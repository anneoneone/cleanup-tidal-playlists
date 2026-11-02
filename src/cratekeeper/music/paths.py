"""Folder layout of the Music folder and helpers for names and paths."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Iterable, Optional

PLAYLISTS_DIR = "Playlists"
AUDIO_EXTENSIONS = (".mp3", ".flac", ".wav", ".aac", ".m4a", ".mp4", ".aiff", ".aif")


class FolderMissingError(RuntimeError):
    """Raised when a configured root folder does not exist (e.g. drive unplugged)."""


def require_folder(path: Path, label: str) -> Path:
    """Return ``path`` or raise if it is missing.

    Refusing to run on a missing root is what keeps an unplugged drive from looking like
    "all files were deleted".
    """
    if not path.is_dir():
        raise FolderMissingError(
            f"{label} not found: {path}. Is the drive connected and the setting right?"
        )
    return path


def playlists_root(music_folder: Path) -> Path:
    """Return the folder that holds one sub-folder per Playlist."""
    return music_folder / PLAYLISTS_DIR


def nfc(value: str) -> str:
    """Return ``value`` in NFC form (macOS file names come back as NFD)."""
    return unicodedata.normalize("NFC", value)


def name_key(value: str) -> str:
    """Return a key for comparing playlist or folder names."""
    return nfc(value).casefold().strip()


def simplify(value: Optional[str]) -> str:
    """Keep only letters and digits (any script), lower-cased."""
    if not value:
        return ""
    return "".join(
        ch for ch in nfc(value).casefold() if unicodedata.category(ch)[0] in "LN"
    )


def is_audio_file(path: Path) -> bool:
    """Return whether ``path`` is a supported audio file (hidden files excluded)."""
    return (
        path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in AUDIO_EXTENSIONS
    )


def list_audio_files(folder: Path, recursive: bool = False) -> list[Path]:
    """Return audio files in ``folder``, sorted by name."""
    if not folder.is_dir():
        return []
    entries: Iterable[Path] = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(p for p in entries if is_audio_file(p))


def resolve_stored_path(raw: str, music_folder: Path) -> Path:
    """Turn a stored path (absolute, or relative to the Music folder) into a path."""
    path = Path(raw)
    return path if path.is_absolute() else music_folder / path


def to_stored_path(path: Path, music_folder: Path) -> str:
    """Store paths under the Music folder relative to it (v1), others absolute."""
    try:
        return nfc(str(path.relative_to(music_folder)))
    except ValueError:
        return nfc(str(path))


def first_existing_file(
    stored_paths: Optional[Iterable[str]], music_folder: Path
) -> Optional[Path]:
    """Return the first stored path that exists on disk."""
    for raw in stored_paths or []:
        candidate = resolve_stored_path(raw, music_folder)
        if candidate.is_file():
            return candidate
    return None
