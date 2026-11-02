"""Refresh Tidal playlists into the database (one implementation for everything).

Per playlist, in one transaction: upsert the playlist and its tracks with full
metadata, set ``in_tidal``/position/date added, and mark removed tracks. Rows of
removed tracks are kept (``in_tidal`` false) so their files stay linked to them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.engine import Database
from ..db.models import DownloadStatus, Playlist, PlaylistSource, Track
from ..jobs import JobContext
from .client import TidalPlaylist, TidalTrack, TrackListing

logger = logging.getLogger(__name__)

SHRINK_LIMIT = 0.5  # abort if fewer than half of the known playlists come back
SHRINK_MIN_KNOWN = 4


class PlaylistShrinkError(RuntimeError):
    """Raised when Tidal returns far fewer playlists than known (likely an error)."""


class TidalSource(Protocol):
    """What the refresh needs from Tidal (``TidalClient`` or a test fake)."""

    def playlists(self) -> list[TidalPlaylist]:
        """Return the user's playlists."""
        ...

    def playlist_tracks(self, playlist_id: str) -> TrackListing:
        """Return all tracks of one playlist."""
        ...


@dataclass
class TidalRefreshStats:
    """Counters of one Tidal refresh."""

    playlists: int = 0
    playlists_created: int = 0
    playlists_renamed: int = 0
    playlists_unchanged: int = 0
    playlists_gone: int = 0
    tracks_added: int = 0
    tracks_removed: int = 0
    duplicates_dropped: int = 0
    incomplete: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def refresh_tidal(
    db: Database,
    source: TidalSource,
    ctx: Optional[JobContext] = None,
    playlist_name: Optional[str] = None,
    *,
    full: bool = False,
    allow_shrink: bool = False,
) -> TidalRefreshStats:
    """Read Tidal playlists into the database."""
    stats = TidalRefreshStats()
    remote = source.playlists()

    if playlist_name is not None:
        key = repo.name_key(playlist_name)
        remote = [p for p in remote if repo.name_key(p.name) == key]
        if not remote:
            raise LookupError(f"No Tidal playlist named {playlist_name!r}")
    elif not allow_shrink:
        with db.session() as session:
            _check_shrink(session, len(remote))

    for index, tidal_playlist in enumerate(remote, start=1):
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(index, len(remote), tidal_playlist.name)
        with db.session() as session:
            _refresh_playlist(session, source, tidal_playlist, full, stats)
        stats.playlists += 1

    if playlist_name is None:
        with db.session() as session:
            _mark_gone(session, {p.id for p in remote}, stats)
    for warning in stats.warnings:
        logger.warning(warning)
    return stats


def _check_shrink(session: Session, remote_count: int) -> None:
    known = int(
        session.scalar(
            select(func.count(Playlist.id)).where(Playlist.in_tidal.is_(True))
        )
        or 0
    )
    if known == 0:
        return
    if remote_count == 0 or (
        known >= SHRINK_MIN_KNOWN and remote_count < known * SHRINK_LIMIT
    ):
        raise PlaylistShrinkError(
            f"Tidal returned {remote_count} playlists, but {known} are known. "
            "Stopping so nothing is marked as removed by mistake. If you really "
            "deleted them, run the sync again with --allow-shrink."
        )


def _refresh_playlist(
    session: Session,
    source: TidalSource,
    remote: TidalPlaylist,
    full: bool,
    stats: TidalRefreshStats,
) -> None:
    playlist = repo.playlist_by_tidal_id(session, remote.id)
    if playlist is None:
        playlist = repo.playlist_by_name(session, remote.name, without_tidal_id=True)
    if playlist is None:
        playlist = Playlist(
            tidal_id=remote.id, name=remote.name, source=PlaylistSource.TIDAL.value
        )
        session.add(playlist)
        session.flush()
        stats.playlists_created += 1
    elif playlist.tidal_id is not None and playlist.name != remote.name:
        logger.info("Tidal playlist renamed: %s -> %s", playlist.name, remote.name)
        stats.playlists_renamed += 1

    unchanged = (
        not full
        and playlist.last_updated_tidal is not None
        and remote.last_updated is not None
        and playlist.last_updated_tidal == remote.last_updated
        and playlist.num_tracks == remote.num_tracks
    )
    _apply_playlist_fields(playlist, remote)
    if unchanged:
        stats.playlists_unchanged += 1
        return

    listing = source.playlist_tracks(remote.id)
    _reconcile_tracks(session, playlist, listing, stats)
    # An incomplete listing forces a full fetch next time.
    playlist.last_updated_tidal = remote.last_updated if listing.complete else None


def _apply_playlist_fields(playlist: Playlist, remote: TidalPlaylist) -> None:
    playlist.tidal_id = remote.id
    playlist.name = remote.name
    playlist.in_tidal = True
    playlist.last_seen_in_tidal = repo.utc_now()
    for name in (
        "description",
        "creator_name",
        "creator_id",
        "duration",
        "num_tracks",
        "num_videos",
        "popularity",
        "public",
        "picture_url",
        "square_picture_url",
        "share_url",
        "listen_url",
        "created",
        "last_updated",
        "last_item_added_at",
    ):
        setattr(playlist, name, getattr(remote, name))


def _reconcile_tracks(
    session: Session,
    playlist: Playlist,
    listing: TrackListing,
    stats: TidalRefreshStats,
) -> None:
    rows = repo.playlist_rows(session, playlist.id)
    seen: set[int] = set()
    now = repo.utc_now()
    for position, remote_track in enumerate(listing.tracks):
        track = _upsert_track(session, remote_track)
        if track.id in seen:
            stats.duplicates_dropped += 1
            continue
        seen.add(track.id)
        row = repo.ensure_row(session, rows, playlist, track)
        if not row.in_tidal:
            stats.tracks_added += 1
        row.in_tidal = True
        row.position = position
        row.removed_from_tidal = None
        if remote_track.date_added is not None:
            row.added_to_tidal = remote_track.date_added
        elif row.added_to_tidal is None:
            row.added_to_tidal = now
        track.last_seen_in_tidal = now

    if not listing.complete:
        message = (
            f"{playlist.name}: Tidal listed {len(listing.tracks)} of "
            f"{listing.expected_count} tracks; removals skipped"
        )
        stats.incomplete.append(playlist.name)
        stats.warnings.append(message)
    else:
        for row in rows.values():
            if row.in_tidal and row.track_id not in seen:
                row.in_tidal = False
                row.removed_from_tidal = now
                stats.tracks_removed += 1
    playlist.track_count_tidal = len(seen)


def _upsert_track(session: Session, remote: TidalTrack) -> Track:
    track = repo.track_by_tidal_id(session, remote.id)
    if track is None:
        track = Track(
            tidal_id=remote.id,
            title=remote.title,
            artist=remote.artist,
            normalized_name="",
            download_status=DownloadStatus.NOT_DOWNLOADED.value,
            tidal_unavailable=False,
        )
        session.add(track)
    track.title = remote.title
    track.artist = remote.artist
    track.normalized_name = repo.normalized_track_name(remote.title, remote.artist)
    track.version = remote.version
    track.album = remote.album
    track.album_artist = remote.album_artist
    track.duration = remote.duration
    track.track_number = remote.track_number
    track.volume_number = remote.volume_number
    track.explicit = remote.explicit
    track.copyright = remote.copyright
    track.popularity = remote.popularity
    track.tidal_release_date = remote.release_date
    track.album_upc = remote.album_upc
    track.album_release_date = remote.album_release_date
    track.album_cover_url = remote.album_cover_url
    track.audio_quality = remote.audio_quality
    track.audio_modes = remote.audio_modes
    if remote.isrc:
        track.isrc = remote.isrc
    if remote.release_date is not None:
        track.year = remote.release_date.year
    session.flush()
    return track


def _mark_gone(
    session: Session, remote_ids: set[str], stats: TidalRefreshStats
) -> None:
    """Playlists that disappeared from Tidal lose their Tidal tracks."""
    now = repo.utc_now()
    gone = session.scalars(
        select(Playlist).where(
            Playlist.in_tidal.is_(True), Playlist.tidal_id.is_not(None)
        )
    ).all()
    for playlist in gone:
        if playlist.tidal_id in remote_ids:
            continue
        playlist.in_tidal = False
        for row in repo.playlist_rows(session, playlist.id).values():
            if row.in_tidal:
                row.in_tidal = False
                row.removed_from_tidal = now
                stats.tracks_removed += 1
        stats.playlists_gone += 1
        logger.info("Tidal playlist gone: %s", playlist.name)
