"""Create database tracks for audio files that have no Tidal track."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..db.models import DownloadStatus, Track
from ..db.repository import normalized_track_name
from .metadata import FileTags


def file_time(path: Path) -> datetime:
    """Return the file's creation time (or mtime) as naive UTC."""
    stat = path.stat()
    timestamp = getattr(stat, "st_birthtime", None) or stat.st_mtime
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)


def title_and_artist(path: Path, tags: Optional[FileTags]) -> tuple[str, str]:
    """Return title and artist from tags, else from an "Artist - Title" file name."""
    title = tags.title if tags and tags.title else None
    artist = tags.artist if tags and tags.artist else None
    if title and artist:
        return title, artist
    stem = path.stem
    if " - " in stem:
        stem_artist, stem_title = (part.strip() for part in stem.split(" - ", 1))
        return title or stem_title or stem, artist or stem_artist or "Unknown Artist"
    return title or stem, artist or "Unknown Artist"


def new_file_track(path: Path, stored_path: str, tags: Optional[FileTags]) -> Track:
    """Build a Track for a file (not added to a session)."""
    title, artist = title_and_artist(path, tags)
    stat = path.stat()
    return Track(
        title=title,
        artist=artist,
        album=tags.album if tags else None,
        isrc=tags.isrc if tags else None,
        duration=int(tags.duration) if tags and tags.duration else None,
        normalized_name=normalized_track_name(title, artist),
        file_paths=[stored_path],
        file_size_bytes=stat.st_size,
        file_format=path.suffix.lstrip(".").lower(),
        file_last_modified=datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).replace(tzinfo=None),
        download_status=DownloadStatus.DOWNLOADED.value,
        tidal_unavailable=False,
    )
