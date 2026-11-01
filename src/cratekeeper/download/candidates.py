"""Which Tidal tracks need a Download, and into which folder."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.models import Playlist, PlaylistTrack, Track
from ..music.paths import PLAYLISTS_DIR, first_existing_file, nfc

_UNSAFE = re.compile(r"[/:\x00]")


@dataclass(frozen=True)
class DownloadCandidate:
    """One Tidal track without a file, and the playlist folder it goes into."""

    track_id: int
    tidal_id: str
    artist: str
    title: str
    playlist_id: int
    playlist_name: str
    folder: str  # stored form, relative to the Music folder


def folder_name(playlist_name: str) -> str:
    """Return a safe folder name for a new playlist (keeps emojis)."""
    cleaned = _UNSAFE.sub("-", nfc(playlist_name)).strip().strip(".")
    return cleaned or "Playlist"


def playlist_folder(playlist: Playlist) -> str:
    """Return the playlist's folder (stored form), choosing one if it has none."""
    return playlist.local_folder_path or f"{PLAYLISTS_DIR}/{folder_name(playlist.name)}"


def find_candidates(
    session: Session, music_folder: Path, playlist_name: Optional[str] = None
) -> list[DownloadCandidate]:
    """Return Tidal tracks currently in a Tidal playlist that have no file anywhere.

    A track in several playlists is downloaded once, into the first playlist's folder
    (by playlist ID).
    """
    stmt = (
        select(PlaylistTrack, Track, Playlist)
        .join(Track, Track.id == PlaylistTrack.track_id)
        .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
        .where(
            PlaylistTrack.in_tidal.is_(True),
            Track.tidal_id.is_not(None),
            Track.tidal_unavailable.is_(False),
        )
        .order_by(Playlist.id, PlaylistTrack.position)
    )
    key = repo.name_key(playlist_name) if playlist_name else None
    seen: set[int] = set()
    result: list[DownloadCandidate] = []
    for _row, track, playlist in session.execute(stmt).tuples():
        if track.id in seen:
            continue
        if key is not None and repo.name_key(playlist.name) != key:
            continue
        seen.add(track.id)
        if first_existing_file(track.file_paths, music_folder) is not None:
            continue
        result.append(
            DownloadCandidate(
                track_id=track.id,
                tidal_id=str(track.tidal_id),
                artist=track.artist,
                title=track.title,
                playlist_id=playlist.id,
                playlist_name=playlist.name,
                folder=playlist_folder(playlist),
            )
        )
    return result
