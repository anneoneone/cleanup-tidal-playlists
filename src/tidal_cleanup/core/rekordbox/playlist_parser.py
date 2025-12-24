"""Playlist name parser for extracting emoji-based metadata."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class PlaylistMetadata:
    """Metadata extracted from a playlist name."""

    playlist_name: str
    raw_name: str
    genre_tags: Set[str]
    party_tags: Set[str]
    energy_tags: Set[str]
    status_tags: Set[str]
    event_year: Optional[str] = None

    @property
    def has_genre_or_party(self) -> bool:
        """Check if playlist has at least one genre or party tag."""
        return bool(self.genre_tags or self.party_tags)

    @property
    def category(self) -> str:
        """Determine top-level category for the playlist."""
        return "Genre" if self.genre_tags else "Events"

    @property
    def all_tags(self) -> Dict[str, Set[str]]:
        """Get all tags organized by group."""
        return {
            "Genre": self.genre_tags,
            "Party": self.party_tags,
            "Energy": self.energy_tags,
            "Status": self.status_tags,
        }

    def get_tags_for_group(self, group: str) -> Set[str]:
        """Get tags for a specific group."""
        return self.all_tags.get(group, set())


class PlaylistNameParser:
    """Parser for extracting metadata from playlist names based on emojis."""

    def __init__(self, config_path: Path) -> None:
        """Initialize parser with emoji mapping configuration.

        Args:
            config_path: Path to the JSON configuration file
        """
        self.config_path = config_path
        self.folder_structure: Dict[str, Union[str, List[str]]] = {}
        self.genre_uncategorized: str = "Uncategorized"
        self.events_misc: str = "Misc"
        self.emoji_mapping: Dict[str, Dict[str, str]] = {}
        self.no_genre_config: Dict[str, str] = {}
        self._load_config()
        self._build_reverse_mapping()

    def _load_config(self) -> None:
        """Load emoji mapping configuration from JSON file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.emoji_mapping = config.get("emoji_to_mytag_mapping", {})
            self.no_genre_config = config.get("no_genre_tag", {})
            self.folder_structure = config.get("folder_structure", {})
            self.genre_uncategorized = str(
                self.folder_structure.get("genre_uncategorized", "Uncategorized")
            )
            self.events_misc = str(self.folder_structure.get("events_misc", "Misc"))

            logger.info("Loaded emoji mapping with %d groups", len(self.emoji_mapping))

        except Exception as e:
            logger.error("Failed to load emoji mapping config: %s", e)
            raise

    def _build_reverse_mapping(self) -> None:
        """Build reverse mapping from emoji to (group, tag_name)."""
        self.emoji_to_group_tag: Dict[str, tuple[str, str]] = {}

        for group, emoji_dict in self.emoji_mapping.items():
            for emoji, tag_name in emoji_dict.items():
                # Map the exact emoji
                self.emoji_to_group_tag[emoji] = (group, tag_name)

                # Also map the base emoji without variation/skin-tone markers so
                # variants like 👵 or 👵🏽 resolve to the same tag as 👵🏻.
                base = self._get_base_emoji(emoji)
                if base != emoji and base not in self.emoji_to_group_tag:
                    self.emoji_to_group_tag[base] = (group, tag_name)

        logger.debug(
            f"Built reverse mapping with {len(self.emoji_to_group_tag)} emojis"
        )

    def parse_playlist_name(self, playlist_name: str) -> PlaylistMetadata:
        """Parse playlist name and extract metadata from emojis.

        Playlist names follow pattern:
        "PLAYLIST NAME [GENRE-EMOJI] or [PARTY-EMOJI] [ENERGY-EMOJI] [STATUS-EMOJI]"

        Args:
            playlist_name: Full playlist name including emojis

        Returns:
            PlaylistMetadata with extracted tags
        """
        clean_name = self._extract_clean_name(playlist_name)

        # Extract all emojis from the playlist name
        emojis = self._extract_emojis(playlist_name)

        # Map emojis to tag categories
        genre_tags, party_tags, energy_tags, status_tags = self._map_emojis_to_tags(
            emojis, playlist_name
        )

        event_year: Optional[str] = None

        # Determine fallback buckets
        if party_tags:
            event_year = self._extract_year_from_name(clean_name)
            if not event_year:
                event_year = self.events_misc

        # If neither Genre nor Party recognized, drop into Uncategorized genre
        if not genre_tags and not party_tags:
            genre_tags.add(self.genre_uncategorized)

        metadata = PlaylistMetadata(
            playlist_name=clean_name,
            raw_name=playlist_name,
            genre_tags=genre_tags,
            party_tags=party_tags,
            energy_tags=energy_tags,
            status_tags=status_tags,
            event_year=event_year,
        )

        logger.info(
            f"Parsed playlist '{playlist_name}': "
            f"Genre={genre_tags}, Party={party_tags}, "
            f"Energy={energy_tags}, Status={status_tags}, Year={event_year}"
        )

        return metadata

    def _map_emojis_to_tags(
        self, emojis: List[str], playlist_name: str
    ) -> tuple[Set[str], Set[str], Set[str], Set[str]]:
        """Map emojis to their respective tag categories."""
        genre_tags: Set[str] = set()
        party_tags: Set[str] = set()
        energy_tags: Set[str] = set()
        status_tags: Set[str] = set()

        for emoji in emojis:
            tag_info = self._lookup_emoji_tag(emoji, playlist_name)
            if tag_info:
                group, tag_name = tag_info
                self._add_tag_to_category(
                    group, tag_name, genre_tags, party_tags, energy_tags, status_tags
                )

        return genre_tags, party_tags, energy_tags, status_tags

    def _lookup_emoji_tag(
        self, emoji: str, playlist_name: str
    ) -> Optional[tuple[str, str]]:
        """Lookup emoji and return (group, tag_name) if found."""
        # Try exact match first
        if emoji in self.emoji_to_group_tag:
            return self.emoji_to_group_tag[emoji]

        # Try stripping skin tone and gender modifiers for base emoji match
        base_emoji = self._get_base_emoji(emoji)
        if base_emoji != emoji and base_emoji in self.emoji_to_group_tag:
            return self.emoji_to_group_tag[base_emoji]

        logger.debug(
            f"Emoji '{emoji}' in playlist '{playlist_name}' not found in mapping"
        )
        return None

    def _add_tag_to_category(
        self,
        group: str,
        tag_name: str,
        genre_tags: Set[str],
        party_tags: Set[str],
        energy_tags: Set[str],
        status_tags: Set[str],
    ) -> None:
        """Add tag to the appropriate category set."""
        if group == "Genre":
            genre_tags.add(tag_name)
        elif group == "Party":
            party_tags.add(tag_name)
        elif group == "Energy":
            energy_tags.add(tag_name)
        elif group == "Status":
            status_tags.add(tag_name)

    def _extract_emojis(self, text: str) -> List[str]:
        """Extract all emojis from text.

        Args:
            text: Text to extract emojis from

        Returns:
            List of emoji characters/sequences
        """
        # Unicode ranges for emojis including ZWJ sequences, skin tones,
        # and gender markers
        emoji_pattern = re.compile(
            "(?:"
            "[\U0001f1e0-\U0001f1ff]{2}|"  # flag sequences
            "[\U0001f600-\U0001f64f]|"  # emoticons
            "[\U0001f300-\U0001f5ff]|"  # symbols & pictographs
            "[\U0001f680-\U0001f6ff]|"  # transport & map symbols
            "[\U00002190-\U000021ff]|"  # Arrows & Letterlike Symbols
            "[\U00002702-\U000027b0]|"  # dingbats
            "[\U000024c2-\U0001f251]|"  # enclosed characters
            "[\U0001f900-\U0001f9ff]|"  # supplemental symbols
            "[\U0001fa00-\U0001faff]|"  # extended pictographs
            "[\U00002600-\U000026ff]"  # miscellaneous symbols
            ")"
            "[\U0001f3fb-\U0001f3ff]?"  # optional skin tone modifier
            "(?:\u200d[\U0001f1e0-\U0001f9ff\u2600-\u26ff\u2700-\u27bf]"
            "[\U0001f3fb-\U0001f3ff]?)*"  # ZWJ sequences
            "[\ufe0e\ufe0f]?",  # optional variation selectors
            flags=re.UNICODE,
        )

        emojis = emoji_pattern.findall(text)
        return emojis

    def _extract_clean_name(self, playlist_name: str) -> str:
        """Extract the clean playlist name without emojis.

        Args:
            playlist_name: Full playlist name

        Returns:
            Clean name without emojis
        """
        # Remove all emojis including flag sequences
        emoji_pattern = re.compile(
            "(?:"
            "[\U0001f1e0-\U0001f1ff]{2}|"  # flag sequences
            "[\U0001f600-\U0001f64f]|"
            "[\U0001f300-\U0001f5ff]|"
            "[\U0001f680-\U0001f6ff]|"
            "[\U00002190-\U000021ff]|"  # Arrows and Letterlike Symbols (includes ↗↘↙↖)
            "[\U00002702-\U000027b0]|"
            "[\U000024c2-\U0001f251]|"
            "[\U0001f900-\U0001f9ff]|"
            "[\U0001fa00-\U0001fa6f]|"
            "[\U00002600-\U000026ff]"
            ")[\ufe0e\ufe0f]?",  # optional variation selectors
            flags=re.UNICODE,
        )

        clean_name = emoji_pattern.sub("", playlist_name).strip()

        return clean_name

    def _get_base_emoji(self, emoji: str) -> str:
        """Strip skin tone and gender modifiers to get base emoji.

        Args:
            emoji: Emoji string (possibly with modifiers)

        Returns:
            Base emoji without skin tone/gender modifiers
        """
        # Remove skin tone modifiers (🏻🏼🏽🏾🏿)
        # Remove ZWJ (zero-width joiner) and following characters
        # Remove variation selectors (️)
        base = re.sub(
            r"[\U0001f3fb-\U0001f3ff]|"  # skin tones
            r"\u200d[\U0001f1e0-\U0001f9ff\u2600-\u26ff\u2700-\u27bf]*|"
            # ZWJ sequences
            r"[\ufe0e\ufe0f]",  # variation selectors
            "",
            emoji,
        )
        return base

    def _extract_year_from_name(self, name: str) -> Optional[str]:
        """Extract year from playlist name.

        Supports formats:
        - 4-digit year: 2025, 2024, etc.
        - 2-digit year at start with date pattern: 25-07-19, 24-12-31, etc.
        """
        # Try 4-digit year first (e.g., "2025")
        match = re.search(r"\b(19|20)\d{2}\b", name)
        if match:
            return match.group(0)

        # Try 2-digit year at the start with date pattern (e.g., "25-07-19")
        # Pattern: YY-MM-DD at the start of the string
        match = re.match(r"^(\d{2})-\d{2}-\d{2}", name)
        if match:
            yy = int(match.group(1))
            # Assume 20xx for years 00-99
            # This will work correctly until year 2100
            return f"20{yy:02d}"

        return None

    def get_tag_name_for_emoji(self, emoji: str) -> Optional[Tuple[str, str]]:
        """Get group and tag name for a specific emoji.

        Args:
            emoji: Emoji character

        Returns:
            Tuple of (group_name, tag_name) or None if not found
        """
        return self.emoji_to_group_tag.get(emoji)

    def get_all_groups(self) -> List[str]:
        """Get all available tag groups.

        Returns:
            List of group names
        """
        return list(self.emoji_mapping.keys())

    def get_emojis_for_group(self, group: str) -> Dict[str, str]:
        """Get all emojis and their tag names for a specific group.

        Args:
            group: Group name (e.g., "Genre", "Party")

        Returns:
            Dictionary mapping emoji to tag name
        """
        return self.emoji_mapping.get(group, {})
