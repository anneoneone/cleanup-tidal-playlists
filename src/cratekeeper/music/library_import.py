"""Add an audio file to a Playlist as a Library track.

The file is copied into the Playlist's Music folder sub-folder, then the Music folder
refresh runs for that one Playlist. An existing file is never overwritten. The next Plan
adds the new Library track to Rekordbox.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ..db import repository as repo
from ..db.engine import Database
from ..db.models import Playlist
from ..download.candidates import playlist_folder
from .paths import (
    AUDIO_EXTENSIONS,
    nfc,
    require_folder,
    resolve_stored_path,
    to_stored_path,
)
from .refresh import refresh_music_folder

logger = logging.getLogger(__name__)


class FileNameError(ValueError):
    """Raised when a file name is not a plain audio file name."""


@dataclass(frozen=True)
class ImportTarget:
    """Where an imported file goes."""

    playlist_name: str
    folder: str  # stored form, relative to the Music folder
    path: Path


@dataclass(frozen=True)
class ImportedTrack:
    """Result of an import."""

    track_id: int
    file_path: str  # stored form
    library_track: bool  # False: the file matched one of the Playlist's Tidal tracks


def check_file_name(name: str) -> str:
    """Return ``name`` in NFC form, or raise :class:`FileNameError`."""
    cleaned = nfc(name).strip()
    if (
        not cleaned
        or cleaned != Path(cleaned).name
        or cleaned.startswith(".")
        or "\x00" in cleaned
    ):
        raise FileNameError(f"Not a valid file name: {name!r}")
    if Path(cleaned).suffix.lower() not in AUDIO_EXTENSIONS:
        allowed = ", ".join(AUDIO_EXTENSIONS)
        raise FileNameError(f"Not an audio file: {cleaned}. Allowed: {allowed}")
    return cleaned


def import_target(
    db: Database, music_folder: Path, playlist_id: int, file_name: str
) -> ImportTarget:
    """Return where the file goes.

    Raises :class:`LookupError`, :class:`FileNameError`, ``FolderMissingError`` or
    ``FileExistsError``.
    """
    name = check_file_name(file_name)
    require_folder(music_folder, "Music folder")
    with db.session() as session:
        playlist = session.get(Playlist, playlist_id)
        if playlist is None:
            raise LookupError(f"Playlist {playlist_id} not found")
        folder = playlist_folder(playlist)
        playlist_name = playlist.name
    target = ImportTarget(
        playlist_name, folder, resolve_stored_path(folder, music_folder) / name
    )
    if target.path.exists():
        raise FileExistsError(_exists_message(target))
    return target


def import_library_track(
    db: Database,
    music_folder: Path,
    playlist_id: int,
    file_name: str,
    source: BinaryIO,
) -> ImportedTrack:
    """Copy ``source`` into the Playlist's folder and refresh that Playlist.

    The caller holds the job lock, so no sync reads the folder meanwhile.
    """
    target = import_target(db, music_folder, playlist_id, file_name)
    target.path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_new_file(source, target.path)
    except FileExistsError as exc:
        raise FileExistsError(_exists_message(target)) from exc
    with db.session() as session:
        playlist = session.get(Playlist, playlist_id)
        if playlist is not None and playlist.local_folder_path is None:
            # Set it now, so the refresh links the new folder to this Playlist.
            playlist.local_folder_path = target.folder
    logger.info("Imported %s into %s", target.path.name, target.folder)

    refresh_music_folder(db, music_folder, playlist_name=target.playlist_name)
    stored = to_stored_path(target.path, music_folder)
    with db.session() as session:
        track = repo.track_by_stored_path(session, stored)
        if track is None:
            raise RuntimeError(f"The refresh did not pick up {stored}")
        return ImportedTrack(
            track_id=track.id, file_path=stored, library_track=track.tidal_id is None
        )


def _exists_message(target: ImportTarget) -> str:
    return f"{target.path.name} is already in the folder {target.folder}"


def _write_new_file(source: BinaryIO, target: Path) -> None:
    """Write ``source`` to ``target``; raise ``FileExistsError`` if it exists.

    The data goes to a hidden file first (the refresh skips hidden files), so a failed
    write never leaves a broken audio file behind.
    """
    partial = target.with_name(f".cratekeeper-{uuid.uuid4().hex[:12]}.part")
    reserved = False
    try:
        with partial.open("xb") as out:
            shutil.copyfileobj(source, out)
        # Claim the name first: os.replace alone would overwrite a file.
        with target.open("xb"):
            reserved = True
        os.replace(partial, target)
    except BaseException:
        partial.unlink(missing_ok=True)
        if reserved:
            target.unlink(missing_ok=True)  # the empty file this call created
        raise
