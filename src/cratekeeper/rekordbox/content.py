"""Find or create Rekordbox collection entries (DjmdContent) for tracks.

Ported from v1 ``RekordboxService.get_or_create_content_from_track`` with two
changes: no title-only match (it linked wrong tracks) and no retry with a
minimal payload (a silent fallback). Artist, album and genre rows are looked up
first and only created when missing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from mutagen import File as MutagenFile
from mutagen import MutagenError
from pyrekordbox.db6 import tables

from ..db.models import Track

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".aiff", ".aif"}
_TEXT_LIMIT = 255
_INT_FIELDS = {"BPM", "TrackNo", "DiscNo", "ReleaseYear", "Length", "BitRate"}


def find_content(
    database: Any,
    path: Path,
    stored_id: Optional[str],
    isrc: Optional[str],
    title: str,
    artist: str,
) -> Optional[Any]:
    """Return existing content: by file path, stored ID, ISRC, then title + artist."""
    by_path = database.get_content(FolderPath=str(path)).first()
    if by_path is not None:
        return by_path
    if stored_id:
        by_id = database.get_content(ID=stored_id)
        if by_id is not None and Path(str(by_id.FolderPath)).is_file():
            return by_id
    if isrc:
        hits = database.get_content(ISRC=isrc).all()
        if len(hits) == 1:
            return hits[0]
    artist_row = database.get_artist(Name=artist).first()
    if artist_row is not None:
        hits = database.get_content(Title=title, ArtistID=artist_row.ID).all()
        if len(hits) == 1:
            return hits[0]
    return None


def import_content(
    database: Any, track: Track, path: Path, genre: Optional[str]
) -> Any:
    """Add ``path`` to the collection with metadata from the track and the file."""
    existing = database.get_content(FolderPath=str(path)).first()
    if existing is not None:
        return existing
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Rekordbox does not support {path.suffix} files: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"File is gone: {path}")
    payload = build_payload(track, path)
    payload["ArtistID"] = ensure_artist(database, track.artist or "Unknown Artist").ID
    payload["AlbumID"] = ensure_album(database, track.album or "Unknown Album").ID
    if genre:
        payload["GenreID"] = ensure_genre(database, genre).ID
    return database.add_content(str(path), **_sanitize(payload))


def ensure_genre(database: Any, name: str) -> Any:
    """Return the genre row, creating it if needed."""
    return database.get_genre(Name=name).first() or database.add_genre(name)


def ensure_artist(database: Any, name: str) -> Any:
    """Return the artist row, creating it if needed."""
    return database.get_artist(Name=name).first() or database.add_artist(name)


def ensure_album(database: Any, name: str) -> Any:
    """Return the album row, creating it if needed."""
    return database.get_album(Name=name).first() or database.add_album(name)


def genre_name(content: Any) -> Optional[str]:
    """Return the content's genre name."""
    genre = getattr(content, "Genre", None)
    return getattr(genre, "Name", None) if genre is not None else None


def build_payload(track: Track, path: Path) -> dict[str, Any]:
    """Return DjmdContent fields from file tags, overridden by Tidal metadata."""
    payload: dict[str, Any] = {"Title": path.stem}
    payload.update(_file_fields(path))
    payload["Title"] = track.title or payload["Title"]
    year = track.year or (
        track.album_release_date.year if track.album_release_date else None
    )
    if year:
        payload["ReleaseYear"] = year
    if track.track_number is not None:
        payload["TrackNo"] = track.track_number
    if track.volume_number is not None:
        payload["DiscNo"] = track.volume_number
    if track.isrc:
        payload["ISRC"] = track.isrc
    if track.version:
        payload["Subtitle"] = track.version
    comments = [payload.pop("Commnt", "")]
    for label, value in (
        ("Tidal UPC", track.album_upc),
        ("Tidal quality", track.audio_quality),
        ("Tidal mode", track.audio_modes),
    ):
        if value:
            comments.append(f"{label}: {value}")
    payload["Commnt"] = " | ".join(c for c in comments if c)
    return payload


def _bpm(value: str) -> Optional[int]:
    try:
        return int(float(value) * 100)  # Rekordbox stores BPM * 100
    except ValueError:
        return None


def _year(value: str) -> Optional[int]:
    return int(value[:4]) if value[:4].isdigit() else None


_FILE_FIELDS: tuple[tuple[str, tuple[str, ...], Callable[[str], Any]], ...] = (
    ("Title", ("TIT2", "TITLE", "title", "\xa9nam"), str),
    ("Subtitle", ("TIT3", "SUBTITLE", "subtitle"), str),
    ("ISRC", ("TSRC", "ISRC", "isrc"), str),
    ("BPM", ("TBPM", "BPM", "bpm"), _bpm),
    ("ReleaseYear", ("TDRC", "TYER", "DATE", "date", "\xa9day"), _year),
    ("Commnt", ("COMM::eng", "COMMENT", "comment", "\xa9cmt"), str),
)


def _file_fields(path: Path) -> dict[str, Any]:
    try:
        audio = MutagenFile(path)
    except (MutagenError, OSError, ValueError) as exc:
        logger.warning("Cannot read tags of %s: %s", path, exc)
        return {}
    tags = getattr(audio, "tags", None) if audio is not None else None
    if not tags:
        return {}
    fields: dict[str, Any] = {}
    for name, keys, convert in _FILE_FIELDS:
        text = _first_tag(tags, keys)
        value = convert(text) if text is not None else None
        if value is not None:
            fields[name] = value
    return fields


def _first_tag(tags: Any, keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        try:
            value = tags.get(key)
        except (KeyError, ValueError):
            continue
        value = getattr(value, "text", value)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    valid = set(tables.DjmdContent.columns())
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in valid or value is None or value == "":
            continue
        if key in _INT_FIELDS:
            try:
                result[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif isinstance(value, str):
            result[key] = value[:_TEXT_LIMIT]
        else:
            result[key] = value
    return result
