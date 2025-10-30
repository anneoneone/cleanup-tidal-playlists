"""Playlist name parser for extracting emoji-based metadata."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

    @property
    def has_genre_or_party(self) -> bool:
        """Check if playlist has at least one genre or party tag."""
        return bool(self.genre_tags or self.party_tags)

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
        self.emoji_mapping: Dict[str, Any] = {}
        self.no_genre_config: Dict[str, str] = {}
        self._load_config()
        self._build_reverse_mapping()

    def _load_config(self) -> None:
        """Load emoji mapping configuration from JSON file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.emoji_mapping = config.get("Track-Metadata", {})
            self.no_genre_config = config.get("no_genre_tag", {})

            logger.info(f"Loaded emoji mapping with {len(self.emoji_mapping)} groups")

        except Exception as e:
            logger.error(f"Failed to load emoji mapping config: {e}")
            raise

    def _normalize_emoji(self, emoji: str) -> str:
        """Normalize emoji by removing modifiers.

        Removes skin tone, gender, and variation selectors.
        This ensures emojis with different representations (e.g., 🏃🏼‍♂️ vs 🏃)
        are treated as the same emoji.

        Args:
            emoji: Raw emoji string

        Returns:
            Normalized emoji without modifiers
        """
        # Remove skin tone modifiers (🏻-🏿)
        emoji = re.sub(r"[\U0001f3fb-\U0001f3ff]", "", emoji)
        # Remove gender modifiers (ZWJ + gender symbol + variation selector)
        emoji = re.sub(r"\u200d[\u2640\u2642]\ufe0f?", "", emoji)
        # Remove variation selectors (️)
        emoji = re.sub(r"[\ufe0e\ufe0f]", "", emoji)
        # Remove zero-width joiners
        emoji = re.sub(r"\u200d", "", emoji)

        return emoji.strip()

    def _build_reverse_mapping(self) -> None:
        """Build reverse mapping from emoji to (group, tag_name)."""
        self.emoji_to_group_tag: Dict[str, tuple[str, str]] = {}

        for group, content in self.emoji_mapping.items():
            # Handle nested structure for Genre group
            if group == "Genre" and isinstance(content, dict):
                # Genre has nested categories (House, Deep House, etc.)
                for _category, emoji_dict in content.items():
                    if not isinstance(emoji_dict, dict):
                        continue
                    for emoji, tag_name in emoji_dict.items():
                        # Normalize emoji when building the mapping
                        normalized = self._normalize_emoji(emoji)
                        self.emoji_to_group_tag[normalized] = (
                            group,
                            tag_name,
                        )
                        logger.debug(
                            f"Mapped emoji '{emoji}' -> "
                            f"'{normalized}' -> {tag_name}"
                        )
            # Handle flat structure for Energy, Status, etc.
            elif isinstance(content, dict):
                for emoji, tag_name in content.items():
                    # Normalize emoji when building the mapping
                    normalized = self._normalize_emoji(emoji)
                    self.emoji_to_group_tag[normalized] = (group, tag_name)
                    logger.debug(
                        f"Mapped emoji '{emoji}' -> '{normalized}' -> {tag_name}"
                    )

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
        # Extract all emojis from the playlist name
        emojis = self._extract_emojis(playlist_name)

        # Initialize tag sets
        genre_tags: Set[str] = set()
        party_tags: Set[str] = set()
        energy_tags: Set[str] = set()
        status_tags: Set[str] = set()

        # Map emojis to tags
        for emoji in emojis:
            # Normalize the emoji before lookup
            normalized_emoji = self._normalize_emoji(emoji)

            if normalized_emoji in self.emoji_to_group_tag:
                group, tag_name = self.emoji_to_group_tag[normalized_emoji]

                if group == "Genre":
                    genre_tags.add(tag_name)
                elif group == "Party":
                    party_tags.add(tag_name)
                elif group == "Energy":
                    energy_tags.add(tag_name)
                elif group == "Status":
                    status_tags.add(tag_name)
            else:
                logger.debug(
                    f"Emoji '{emoji}' (normalized: '{normalized_emoji}') "
                    f"in playlist '{playlist_name}' not found in mapping"
                )

        metadata = PlaylistMetadata(
            playlist_name=self._extract_clean_name(playlist_name),
            raw_name=playlist_name,
            genre_tags=genre_tags,
            party_tags=party_tags,
            energy_tags=energy_tags,
            status_tags=status_tags,
        )

        # Validate that at least Genre or Party is present
        if not metadata.has_genre_or_party:
            logger.warning(
                f"Playlist '{playlist_name}' has no Genre or Party tags. "
                "At least one is expected."
            )

        logger.info(
            f"Parsed playlist '{playlist_name}': "
            f"Genre={genre_tags}, Party={party_tags}, "
            f"Energy={energy_tags}, Status={status_tags}"
        )

        return metadata

    def _extract_emojis(self, text: str) -> List[str]:
        """Extract all emojis from text.

        Args:
            text: Text to extract emojis from

        Returns:
            List of emoji characters/sequences
        """
        # Unicode ranges for emojis including complex sequences
        emoji_pattern = re.compile(
            "(?:"
            "[\U0001f1e0-\U0001f1ff]{2}|"  # flag sequences
            "[\U0001f600-\U0001f64f]"  # emoticons
            "[\U0001f3fb-\U0001f3ff]?"  # skin tone modifier
            "(?:\u200d[\u2640\u2642]\ufe0f?)?|"  # gender modifier
            "[\U0001f300-\U0001f5ff]"  # symbols & pictographs
            "[\U0001f3fb-\U0001f3ff]?"  # skin tone
            "(?:\u200d[\u2640\u2642]\ufe0f?)?|"  # gender
            "[\U0001f680-\U0001f6ff]|"  # transport & map symbols
            "[\U00002702-\U000027b0]|"  # dingbats
            "[\U000024c2-\U0001f251]|"  # enclosed characters
            "[\U0001f900-\U0001f9ff]"  # supplemental symbols
            "[\U0001f3fb-\U0001f3ff]?"  # skin tone
            "(?:\u200d[\u2640\u2642]\ufe0f?)?|"  # gender
            "[\U0001fa00-\U0001faff]|"  # extended pictographs
            "[\U00002600-\U000026ff]"  # miscellaneous symbols
            ")[\ufe0e\ufe0f]?",  # variation selector
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
        # Remove all emojis including flag sequences and modifiers
        emoji_pattern = re.compile(
            "(?:"
            "[\U0001f1e0-\U0001f1ff]{2}|"  # flag sequences
            "[\U0001f600-\U0001f64f]|"
            "[\U0001f300-\U0001f5ff]|"
            "[\U0001f680-\U0001f6ff]|"
            "[\U00002702-\U000027b0]|"
            "[\U000024c2-\U0001f251]|"
            "[\U0001f900-\U0001f9ff]|"
            "[\U0001fa00-\U0001faff]|"  # extended pictographs
            "[\U00002600-\U000026ff]"
            ")[\ufe0e\ufe0f]?[\u200d\ufe0f]?[\U0001f3fb-\U0001f3ff]?"
            "[\u200d]?[♂♀]?[\ufe0f]?",
            flags=re.UNICODE,
        )

        clean_name = emoji_pattern.sub("", playlist_name).strip()

        return clean_name

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
        result: Dict[str, str] = self.emoji_mapping.get(group, {})
        return result
