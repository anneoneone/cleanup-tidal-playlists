"""Playlist emojis → Playlist tags, Folder placement and Rekordbox names.

Ported from v1 (``playlist_parser.py`` and ``snapshot_service.py``) with the same
rules. The mapping file (see ``defaults/tag_mapping.json``) lists emojis per
group (Genre, Energy, Status, Party) and the folder structure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_EMOJI = re.compile(
    "(?:"
    "[\U0001f1e0-\U0001f1ff]{2}|"  # flags
    "[\U0001f600-\U0001f64f]|"
    "[\U0001f300-\U0001f5ff]|"
    "[\U0001f680-\U0001f6ff]|"
    "[\U00002190-\U000021ff]|"  # arrows
    "[\U00002702-\U000027b0]|"
    "[\U000024c2-\U0001f251]|"
    "[\U0001f900-\U0001f9ff]|"
    "[\U0001fa00-\U0001faff]|"
    "[\U00002600-\U000026ff]"
    ")"
    "[\U0001f3fb-\U0001f3ff]?"  # skin tone
    "(?:‍[\U0001f1e0-\U0001f9ff☀-⛿✀-➿][\U0001f3fb-\U0001f3ff]?)*"
    "[︎️]?",
    flags=re.UNICODE,
)
_EMOJI_STRIP = re.compile(
    "(?:"
    "[\U0001f1e0-\U0001f1ff]{2}|"
    "[\U0001f600-\U0001f64f]|"
    "[\U0001f300-\U0001f5ff]|"
    "[\U0001f680-\U0001f6ff]|"
    "[\U00002190-\U000021ff]|"
    "[\U00002702-\U000027b0]|"
    "[\U000024c2-\U0001f251]|"
    "[\U0001f900-\U0001f9ff]|"
    "[\U0001fa00-\U0001fa6f]|"
    "[\U00002600-\U000026ff]"
    ")[︎️]?",
    flags=re.UNICODE,
)
_MODIFIERS = re.compile(
    r"[\U0001f3fb-\U0001f3ff]|" r"‍[\U0001f1e0-\U0001f9ff☀-⛿✀-➿]*|" r"[︎️]"
)


@dataclass(frozen=True)
class PlaylistTags:
    """What a playlist name says: clean name and Playlist tags per group."""

    clean_name: str
    raw_name: str
    genre: frozenset[str] = field(default_factory=frozenset)
    party: frozenset[str] = field(default_factory=frozenset)
    energy: frozenset[str] = field(default_factory=frozenset)
    status: frozenset[str] = field(default_factory=frozenset)
    event_year: Optional[str] = None


class NameRules:
    """Applies a Playlist tag mapping to playlist names."""

    def __init__(self, mapping: dict[str, Any]) -> None:
        """Build the rules from a parsed mapping file."""
        groups: dict[str, dict[str, str]] = mapping.get("emoji_to_mytag_mapping", {})
        folders: dict[str, Any] = mapping.get("folder_structure", {})
        self.groups = groups
        self.genre_root = str(folders.get("genre_root", "Genre"))
        self.uncategorized = str(folders.get("genre_uncategorized", "Uncategorized"))
        self.default_status = str(folders.get("genre_default_status", "Archived"))
        self.categories: dict[str, list[str]] = folders.get("genre_categories", {})
        self.events_root = str(folders.get("events_root", "Events"))
        self.events_misc = str(folders.get("events_misc", "Misc"))
        self._lookup: dict[str, tuple[str, str]] = {}
        for group, emojis in groups.items():
            for emoji, tag in emojis.items():
                self._lookup[emoji] = (group, tag)
                base = _MODIFIERS.sub("", emoji)
                self._lookup.setdefault(base, (group, tag))

    @classmethod
    def from_file(cls, path: Path) -> NameRules:
        """Load rules from a mapping JSON file."""
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def parse(self, name: str) -> PlaylistTags:
        """Read the Playlist tags from a playlist name."""
        tags: dict[str, set[str]] = {
            "Genre": set(),
            "Party": set(),
            "Energy": set(),
            "Status": set(),
        }
        for emoji in _EMOJI.findall(name):
            hit = self._lookup.get(emoji) or self._lookup.get(_MODIFIERS.sub("", emoji))
            if hit and hit[0] in tags:
                tags[hit[0]].add(hit[1])
        clean = clean_name(name)
        event_year = None
        if tags["Party"]:
            event_year = _event_year(clean) or self.events_misc
        if not tags["Genre"] and not tags["Party"]:
            tags["Genre"].add(self.uncategorized)
        return PlaylistTags(
            clean_name=clean,
            raw_name=name,
            genre=frozenset(tags["Genre"]),
            party=frozenset(tags["Party"]),
            energy=frozenset(tags["Energy"]),
            status=frozenset(tags["Status"]),
            event_year=event_year,
        )

    def rekordbox_name(self, tags: PlaylistTags, include_status: bool = True) -> str:
        """Return the emoji-free Rekordbox name: name + energy + non-default status."""
        name = tags.clean_name
        if tags.energy:
            name = f"{name} {sorted(tags.energy)[0]}"
        if include_status:
            status = sorted(tags.status)[0] if tags.status else self.default_status
            if status != self.default_status:
                name = f"{name} {status}"
        return name.strip()

    def folder_path(self, tags: PlaylistTags) -> list[str]:
        """Return the Folder placement, e.g. ``["Genre", "Techno", "Archived"]``."""
        real_genres = sorted(g for g in tags.genre if g != self.uncategorized)
        if real_genres:
            status = sorted(tags.status)[0] if tags.status else self.default_status
            return [self.genre_root, self.category(real_genres[0]), status]
        if tags.party:
            year = tags.event_year or self.events_misc
            return [self.events_root, sorted(tags.party)[0], year]
        if tags.status:
            return [self.genre_root, self.uncategorized, sorted(tags.status)[0]]
        return [self.genre_root, self.uncategorized, self.default_status]

    def category(self, genre: str) -> str:
        """Return the genre's category folder ("Other Genres" if unlisted)."""
        for category, genres in self.categories.items():
            if genre in genres:
                return category
        return "Other Genres" if self.categories else genre

    def genre(self, tags: PlaylistTags) -> Optional[str]:
        """Return the genre given to tracks of this playlist (first real genre)."""
        real = sorted(g for g in tags.genre if g != self.uncategorized)
        return real[0] if real else None


def clean_name(name: str) -> str:
    """Remove emojis and extra spaces from a playlist name."""
    cleaned = _EMOJI_STRIP.sub("", name)
    cleaned = re.sub(r"[‍︎️]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _event_year(name: str) -> Optional[str]:
    match = re.search(r"\b(19|20)\d{2}\b", name)
    if match:
        return match.group(0)
    match = re.match(r"^(\d{2})-\d{2}-\d{2}", name)
    if match:
        return f"20{int(match.group(1)):02d}"
    return None


EPOCH = datetime(1970, 1, 1)


def added_date(
    added_to_tidal: Optional[datetime],
    added_to_local: Optional[datetime],
    track_created: Optional[datetime],
) -> datetime:
    """Return the date used to order new tracks (v1 rule), as naive UTC."""
    for value in (added_to_tidal, added_to_local, track_created):
        if value is not None:
            return value.replace(tzinfo=None) if value.tzinfo else value
    return EPOCH
