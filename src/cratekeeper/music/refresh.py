"""Refresh the Music folder into the database.

Each sub-folder of ``<music>/Playlists`` belongs to one Playlist: a Tidal playlist
(its downloads) or a Local playlist (a folder with no Tidal playlist). Files that
match one of the playlist's Tidal tracks are linked to that track. All other files
become Local tracks of the playlist. Nothing on disk is changed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.engine import Database
from ..db.models import Playlist, PlaylistSource, PlaylistTrack, Track
from ..jobs import JobContext
from .matching import Candidate, TagReader, match_files
from .metadata import FileTags, read_file_tags
from .paths import (
    PLAYLISTS_DIR,
    list_audio_files,
    name_key,
    nfc,
    playlists_root,
    require_folder,
    resolve_stored_path,
    to_stored_path,
)
from .tracks import file_time, new_file_track

logger = logging.getLogger(__name__)


@dataclass
class MusicRefreshStats:
    """Counters of one Music folder refresh."""

    folders: int = 0
    local_playlists_created: int = 0
    files: int = 0
    linked_to_tidal: int = 0
    local_tracks: int = 0
    local_tracks_gone: int = 0
    paths_dropped: int = 0
    warnings: list[str] = field(default_factory=list)


def refresh_music_folder(
    db: Database,
    music_folder: Path,
    ctx: Optional[JobContext] = None,
    playlist_name: Optional[str] = None,
) -> MusicRefreshStats:
    """Scan ``<music>/Playlists`` and update file paths and Local tracks."""
    require_folder(music_folder, "Music folder")
    stats = MusicRefreshStats()
    root = playlists_root(music_folder)
    folders = (
        sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
        if root.is_dir()
        else []
    )

    with db.session() as session:
        assignments = _assign_folders(session, folders, stats)
    if playlist_name is not None:
        key = name_key(playlist_name)
        assignments = [
            (folder, pid, name)
            for folder, pid, name in assignments
            if name_key(name) == key or name_key(folder.name) == key
        ]

    @lru_cache(maxsize=None)
    def read_tags(path: Path) -> Optional[FileTags]:
        return read_file_tags(path)

    total = len(assignments)
    for index, (folder, playlist_id, name) in enumerate(assignments, start=1):
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(index, total, name)
        with db.session() as session:
            _refresh_playlist_folder(
                session, folder, playlist_id, music_folder, read_tags, stats
            )
        stats.folders += 1

    if playlist_name is None:
        with db.session() as session:
            _clear_missing_folders(session, music_folder, stats)
    logger.info(
        "Music folder: %d folders, %d files, %d linked to Tidal tracks, "
        "%d Local tracks",
        stats.folders,
        stats.files,
        stats.linked_to_tidal,
        stats.local_tracks,
    )
    return stats


def _assign_folders(
    session: Session, folders: list[Path], stats: MusicRefreshStats
) -> list[tuple[Path, int, str]]:
    """Map each folder to a Playlist, creating Local playlists for unknown folders."""
    playlists = repo.all_playlists(session)
    by_folder = {
        name_key(p.local_folder_path): p for p in playlists if p.local_folder_path
    }
    result: list[tuple[Path, int, str]] = []
    claimed: set[int] = set()
    for folder in folders:
        stored = f"{PLAYLISTS_DIR}/{nfc(folder.name)}"
        playlist = by_folder.get(name_key(stored))
        if playlist is None:
            playlist = next(
                (
                    p
                    for p in playlists
                    if name_key(p.name) == name_key(folder.name)
                    and p.local_folder_path is None
                    and p.id not in claimed
                ),
                None,
            )
            if playlist is not None:
                playlist.local_folder_path = stored
        if playlist is None:
            playlist = Playlist(
                name=nfc(folder.name),
                source=PlaylistSource.LOCAL.value,
                local_folder_path=stored,
                in_tidal=False,
            )
            session.add(playlist)
            session.flush()
            stats.local_playlists_created += 1
            logger.info("New Local playlist from folder: %s", folder.name)
        claimed.add(playlist.id)
        result.append((folder, playlist.id, playlist.name))
    return result


def _refresh_playlist_folder(
    session: Session,
    folder: Path,
    playlist_id: int,
    music_folder: Path,
    read_tags: TagReader,
    stats: MusicRefreshStats,
) -> None:
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        return
    files = list_audio_files(folder)
    stats.files += len(files)
    rows = repo.playlist_rows(session, playlist.id)
    tracks: dict[int, Track] = {}
    if rows:
        query = select(Track).where(Track.id.in_(list(rows)))
        tracks = {t.id: t for t in session.scalars(query)}

    def stored_path_of(path: Path) -> str:
        return to_stored_path(path, music_folder)

    result = match_files(files, _candidates(tracks), stored_path_of, read_tags)
    for path, track_id in result.matches.items():
        stored = stored_path_of(path)
        repo.add_file_path(tracks[track_id], stored)
        _release_path_from_others(session, stored, track_id)
        stats.linked_to_tidal += 1

    local_ids = _mark_local_tracks(
        session, playlist, rows, result.unmatched, stored_path_of, read_tags
    )
    stats.local_tracks += len(local_ids)
    for row in rows.values():
        if row.in_local and row.track_id not in local_ids:
            row.in_local = False
            stats.local_tracks_gone += 1

    stats.paths_dropped += _drop_missing_paths(tracks.values(), folder, music_folder)
    playlist.track_count_local = len(files)


def _candidates(tracks: dict[int, Track]) -> list[Candidate]:
    return [
        Candidate(
            track_id=t.id,
            tidal_id=t.tidal_id,
            artist=t.artist,
            title=t.title,
            version=t.version,
            isrc=t.isrc,
            stored_paths=frozenset(t.file_paths or []),
        )
        for t in tracks.values()
        if t.tidal_id
    ]


def _mark_local_tracks(
    session: Session,
    playlist: Playlist,
    rows: dict[int, PlaylistTrack],
    files: list[Path],
    stored_path_of: Callable[[Path], str],
    read_tags: TagReader,
) -> set[int]:
    """Make unmatched files Local tracks.

    Returns their track IDs.
    """
    local_ids: set[int] = set()
    for path in files:
        stored = stored_path_of(path)
        owner = repo.track_by_stored_path(session, stored)
        if owner is not None and owner.tidal_id is not None:
            continue  # belongs to a Tidal track: never a Local track
        if owner is None:
            owner = new_file_track(path, stored, read_tags(path))
            session.add(owner)
            session.flush()
        row = repo.ensure_row(session, rows, playlist, owner)
        row.in_local = True
        if row.added_to_local is None:
            row.added_to_local = file_time(path)
        local_ids.add(owner.id)
    return local_ids


def _drop_missing_paths(
    tracks: Iterable[Track], folder: Path, music_folder: Path
) -> int:
    """Remove stored paths into ``folder`` whose file is gone."""
    dropped = 0
    for track in tracks:
        for raw in list(track.file_paths or []):
            path = resolve_stored_path(raw, music_folder)
            if path.parent == folder and not path.exists():
                repo.remove_file_path(track, raw)
                dropped += 1
    return dropped


def _release_path_from_others(session: Session, stored: str, owner_id: int) -> None:
    """Remove ``stored`` from tracks other than its owner (fixes v1 duplicates)."""
    other = repo.track_by_stored_path(session, stored)
    while other is not None and other.id != owner_id:
        repo.remove_file_path(other, stored)
        session.flush()
        other = repo.track_by_stored_path(session, stored)


def _clear_missing_folders(
    session: Session, music_folder: Path, stats: MusicRefreshStats
) -> None:
    """Playlists whose folder was deleted lose their Local tracks."""
    for playlist in repo.all_playlists(session):
        if not playlist.local_folder_path:
            continue
        if resolve_stored_path(playlist.local_folder_path, music_folder).is_dir():
            continue
        for row in repo.playlist_rows(session, playlist.id).values():
            if row.in_local:
                row.in_local = False
                stats.local_tracks_gone += 1
        playlist.track_count_local = 0
