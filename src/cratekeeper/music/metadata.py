"""Read file tags (title, artist, ISRC, Tidal URL) from audio files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mutagen import File as MutagenFile
from mutagen import MutagenError

logger = logging.getLogger(__name__)

TIDAL_TRACK_URL = re.compile(r"/track/(\d+)")


@dataclass(frozen=True)
class FileTags:
    """The tags Cratekeeper uses to identify a file."""

    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    isrc: Optional[str] = None
    url: Optional[str] = None
    duration: Optional[float] = None

    @property
    def tidal_id(self) -> Optional[str]:
        """Return the Tidal track ID from the share URL tag, if present."""
        if not self.url:
            return None
        match = TIDAL_TRACK_URL.search(self.url)
        return match.group(1) if match else None


def read_file_tags(path: Path) -> Optional[FileTags]:
    """Return the file's tags, or None if mutagen cannot read it."""
    try:
        easy = MutagenFile(path, easy=True)
        raw = MutagenFile(path)
    except (MutagenError, OSError, ValueError) as exc:
        logger.warning("Cannot read tags of %s: %s", path, exc)
        return None
    if easy is None:
        return None

    isrc = _easy(easy, "isrc") or _raw(raw, ("isrc", "TSRC", "ISRC"))
    url = _easy(easy, "url") or _raw(raw, ("\xa9url", "TXXX:URL", "URL", "WOAS"))
    return FileTags(
        title=_easy(easy, "title"),
        artist=_easy(easy, "artist"),
        album=_easy(easy, "album"),
        isrc=isrc.upper() if isrc else None,
        url=url,
        duration=getattr(getattr(easy, "info", None), "length", None),
    )


def _easy(audio: Any, key: str) -> Optional[str]:
    tags = getattr(audio, "tags", None)
    if not tags:
        return None
    try:
        value = tags.get(key)
    except (KeyError, ValueError):
        return None
    return _first_text(value)


def _raw(audio: Any, keys: tuple[str, ...]) -> Optional[str]:
    tags = getattr(audio, "tags", None)
    if not tags:
        return None
    for key in keys:
        try:
            value = tags.get(key)
        except (KeyError, ValueError):
            continue
        text = _first_text(getattr(value, "text", value))
        if text:
            return text
    return None


def _first_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).strip() if value is not None else ""
    return text or None
