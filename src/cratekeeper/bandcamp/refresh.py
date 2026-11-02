"""Refresh the Bandcamp folder into the database.

Each direct sub-folder of the Bandcamp folder is one Playlist. A folder with the same
name as an existing Playlist (e.g. a Tidal playlist) joins that Playlist. If the
Bandcamp folder is missing (drive unplugged) the step is skipped and all Bandcamp flags
stay as they are.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.engine import Database
from ..db.models import Playlist, PlaylistSource, PlaylistTrack
from ..jobs import JobContext
from ..music.metadata import read_file_tags
from ..music.paths import list_audio_files, name_key, nfc
from ..music.tracks import file_time, new_file_track

logger = logging.getLogger(__name__)


@dataclass
class BandcampRefreshStats:
    """Counters of one Bandcamp refresh."""

    skipped: Optional[str] = None
    folders: int = 0
    playlists_created: int = 0
    files: int = 0
    tracks_created: int = 0
    tracks_gone: int = 0
    playlists_gone: int = 0
    warnings: list[str] = field(default_factory=list)


def refresh_bandcamp(
    db: Database,
    bandcamp_folder: Optional[Path],
    ctx: Optional[JobContext] = None,
    playlist_name: Optional[str] = None,
) -> BandcampRefreshStats:
    """Scan the Bandcamp folder and update ``in_bandcamp`` flags."""
    stats = BandcampRefreshStats()
    if bandcamp_folder is None:
        stats.skipped = "No Bandcamp folder configured"
        return stats
    if not bandcamp_folder.is_dir():
        stats.skipped = f"Bandcamp folder not found: {bandcamp_folder} (skipped)"
        stats.warnings.append(stats.skipped)
        logger.warning(stats.skipped)
        return stats

    folders = sorted(
        p
        for p in bandcamp_folder.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if playlist_name is not None:
        folders = [f for f in folders if name_key(f.name) == name_key(playlist_name)]

    for index, folder in enumerate(folders, start=1):
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(index, len(folders), folder.name)
        with db.session() as session:
            _refresh_folder(session, folder, stats)
        stats.folders += 1

    if playlist_name is None:
        with db.session() as session:
            _clear_vanished_folders(session, {name_key(f.name) for f in folders}, stats)
    return stats


def _refresh_folder(
    session: Session, folder: Path, stats: BandcampRefreshStats
) -> None:
    playlist = repo.playlist_by_name(session, folder.name)
    if playlist is None:
        playlist = Playlist(
            name=nfc(folder.name), source=PlaylistSource.LOCAL.value, in_tidal=False
        )
        session.add(playlist)
        session.flush()
        stats.playlists_created += 1

    rows = repo.playlist_rows(session, playlist.id)
    next_position = 1 + max((r.position or 0 for r in rows.values()), default=0)
    seen: set[int] = set()
    for path in list_audio_files(folder, recursive=True):
        stats.files += 1
        stored = nfc(str(path))
        track = repo.track_by_stored_path(session, stored)
        if track is None:
            track = new_file_track(path, stored, read_file_tags(path))
            session.add(track)
            session.flush()
            stats.tracks_created += 1
        is_new_row = track.id not in rows
        row = repo.ensure_row(session, rows, playlist, track)
        row.in_bandcamp = True
        if is_new_row:
            row.position = next_position
            next_position += 1
        if row.added_to_local is None:
            row.added_to_local = file_time(path)
        seen.add(track.id)

    for row in rows.values():
        if row.in_bandcamp and row.track_id not in seen:
            row.in_bandcamp = False
            stats.tracks_gone += 1


def _clear_vanished_folders(
    session: Session, folder_keys: set[str], stats: BandcampRefreshStats
) -> None:
    """Playlists whose Bandcamp folder was deleted lose their Bandcamp tracks."""
    playlist_ids = session.scalars(
        select(PlaylistTrack.playlist_id)
        .where(PlaylistTrack.in_bandcamp.is_(True))
        .distinct()
    ).all()
    for playlist_id in playlist_ids:
        playlist = session.get(Playlist, playlist_id)
        if playlist is None or name_key(playlist.name) in folder_keys:
            continue
        for row in repo.playlist_rows(session, playlist_id).values():
            row.in_bandcamp = False
        stats.playlists_gone += 1
        logger.info("Bandcamp folder gone: %s", playlist.name)
