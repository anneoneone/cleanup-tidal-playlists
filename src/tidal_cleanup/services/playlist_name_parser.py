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
    set_tags: Set[str]
    radio_moafunk_tags: Set[str]
    energy_tags: Set[str]
    status_tags: Set[str]

    @property
    def has_genre_or_event(self) -> bool:
        """Check if playlist has at least one genre or event tag."""
        return bool(
            self.genre_tags
            or self.party_tags
            or self.set_tags
            or self.radio_moafunk_tags
        )

    @property
    def has_genre_or_party(self) -> bool:
        """Check if playlist has at least one genre or party tag.

        Deprecated: Use has_genre_or_event instead.
        """
        return self.has_genre_or_event

    @property
    def all_tags(self) -> Dict[str, Set[str]]:
        """Get all tags organized by group."""
        return {
            "Genre": self.genre_tags,
            "Party": self.party_tags,
            "Set": self.set_tags,
            "Radio Moafunk": self.radio_moafunk_tags,
            "Energy": self.energy_tags,
            "Status": self.status_tags,
        }

    @property
    def event_tags(self) -> Dict[str, Set[str]]:
        """Get only event tags (Party, Set, Radio Moafunk)."""
        return {
            "Party": self.party_tags,
            "Set": self.set_tags,
            "Radio Moafunk": self.radio_moafunk_tags,
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
            self.event_mapping = config.get("Event-Metadata", {})
            self.no_genre_config = config.get("no_genre_tag", {})

            logger.info(
                f"Loaded emoji mapping with {len(self.emoji_mapping)} "
                f"track groups and {len(self.event_mapping)} event types"
            )

        except Exception as e:
            logger.error(f"Failed to load emoji mapping config: {e}")
            raise

    def _normalize_emoji(
        self, emoji: str, preserve_variation_selector: bool = False
    ) -> str:
        """Normalize emoji by removing modifiers.

        Removes skin tone and gender modifiers. Optionally preserves variation selectors
        for emojis like arrows where the variation selector is semantically important.

        This ensures emojis with different representations (e.g., 🏃🏼‍♂️ vs 🏃)
        are treated as the same emoji, while allowing Energy arrows to retain their
        variation selectors (↗️ vs ↗).

        Args:
            emoji: Raw emoji string
            preserve_variation_selector: If True, keep variation selectors (FE0E/FE0F).
                                         Use True for Energy emojis (arrows).

        Returns:
            Normalized emoji without modifiers (except variation selector if preserved)
        """
        # Remove skin tone modifiers (🏻-🏿)
        emoji = re.sub(r"[\U0001f3fb-\U0001f3ff]", "", emoji)
        # Remove gender modifiers (ZWJ + gender symbol + variation selector)
        emoji = re.sub(r"\u200d[\u2640\u2642]\ufe0f?", "", emoji)
        # Remove zero-width joiners
        emoji = re.sub(r"\u200d", "", emoji)

        # Only remove variation selectors if not preserving them
        if not preserve_variation_selector:
            # Remove variation selectors (️)
            emoji = re.sub(r"[\ufe0e\ufe0f]", "", emoji)

        return emoji.strip()

    def _build_reverse_mapping(self) -> None:
        """Build reverse mapping from emoji to (group, tag_name)."""
        self.emoji_to_group_tag: Dict[str, tuple[str, str]] = {}

        # Process Track-Metadata
        for group, content in self.emoji_mapping.items():
            # Handle nested structure for Genre group
            if group == "Genre" and isinstance(content, dict):
                # Genre has nested categories (House, Deep House, etc.)
                for _category, emoji_dict in content.items():
                    if not isinstance(emoji_dict, dict):
                        continue
                    for emoji, tag_name in emoji_dict.items():
                        # Normalize emoji when building the mapping
                        # Genre emojis should have skin tones removed
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
                    # For Energy group, preserve variation selectors
                    # (important for arrows). For other groups (Status, etc.),
                    # remove all modifiers
                    preserve_vs = group == "Energy"
                    normalized = self._normalize_emoji(emoji, preserve_vs)
                    self.emoji_to_group_tag[normalized] = (group, tag_name)
                    logger.debug(
                        f"Mapped {group} emoji '{emoji}' -> "
                        f"'{normalized}' -> {tag_name} "
                        f"(preserve_variation_selector={preserve_vs})"
                    )

        # Process Event-Metadata (🎉: Party, 🎶: Set, 🎙️: Radio Moafunk)
        # Each event type is its own MyTag group
        for emoji, event_type in self.event_mapping.items():
            normalized = self._normalize_emoji(emoji)
            # The event_type itself is the group name (Party, Set, Radio Moafunk)
            self.emoji_to_group_tag[normalized] = (event_type, event_type)
            logger.debug(
                f"Mapped event emoji '{emoji}' -> "
                f"'{normalized}' -> group={event_type}"
            )

        logger.debug(
            f"Built reverse mapping with {len(self.emoji_to_group_tag)} emojis"
        )

    def _lookup_emoji_in_mapping(self, emoji: str) -> Optional[Tuple[str, str]]:
        """Look up emoji in mapping, trying both with and without variation selector.

        Args:
            emoji: The emoji to look up

        Returns:
            Tuple of (group, tag_name) if found, None otherwise
        """
        # First, try with variation selector preserved (for Energy arrows)
        normalized_with_vs = self._normalize_emoji(
            emoji, preserve_variation_selector=True
        )
        # Then, try without variation selector (for Genre, Status, etc.)
        normalized_without_vs = self._normalize_emoji(
            emoji, preserve_variation_selector=False
        )

        if normalized_with_vs in self.emoji_to_group_tag:
            return self.emoji_to_group_tag[normalized_with_vs]
        elif normalized_without_vs in self.emoji_to_group_tag:
            return self.emoji_to_group_tag[normalized_without_vs]

        return None

    def _add_tag_to_sets(
        self,
        group: str,
        tag_name: str,
        clean_name: str,
        genre_tags: Set[str],
        party_tags: Set[str],
        set_tags: Set[str],
        radio_moafunk_tags: Set[str],
        energy_tags: Set[str],
        status_tags: Set[str],
    ) -> None:
        """Add a tag to the appropriate tag set based on its group.

        Args:
            group: The group name (Genre, Party, Energy, etc.)
            tag_name: The tag name/value
            clean_name: Clean playlist name for event tags
            genre_tags: Set to add genre tags to
            party_tags: Set to add party tags to
            set_tags: Set to add set tags to
            radio_moafunk_tags: Set to add radio moafunk tags to
            energy_tags: Set to add energy tags to
            status_tags: Set to add status tags to
        """
        if group == "Genre":
            genre_tags.add(tag_name)
        elif group == "Party":
            party_tags.add(clean_name)
        elif group == "Set":
            set_tags.add(clean_name)
        elif group == "Radio Moafunk":
            radio_moafunk_tags.add(clean_name)
        elif group == "Energy":
            energy_tags.add(tag_name)
        elif group == "Status":
            status_tags.add(tag_name)

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

        # Extract clean name (without emojis) for event playlists
        clean_name = self._extract_clean_name(playlist_name)

        # Initialize tag sets
        genre_tags: Set[str] = set()
        party_tags: Set[str] = set()
        set_tags: Set[str] = set()
        radio_moafunk_tags: Set[str] = set()
        energy_tags: Set[str] = set()
        status_tags: Set[str] = set()

        # Map emojis to tags
        for emoji in emojis:
            result = self._lookup_emoji_in_mapping(emoji)

            if result:
                group, tag_name = result
                self._add_tag_to_sets(
                    group,
                    tag_name,
                    clean_name,
                    genre_tags,
                    party_tags,
                    set_tags,
                    radio_moafunk_tags,
                    energy_tags,
                    status_tags,
                )
            else:
                # Log when emoji is not found
                logger.debug(
                    f"Emoji '{emoji}' in playlist '{playlist_name}' "
                    f"not found in mapping"
                )

        metadata = PlaylistMetadata(
            playlist_name=clean_name,
            raw_name=playlist_name,
            genre_tags=genre_tags,
            party_tags=party_tags,
            set_tags=set_tags,
            radio_moafunk_tags=radio_moafunk_tags,
            energy_tags=energy_tags,
            status_tags=status_tags,
        )

        # Validate that at least Genre or Event is present
        if not metadata.has_genre_or_event:
            logger.warning(
                f"Playlist '{playlist_name}' has no Genre or Event tags. "
                "At least one is expected."
            )

        logger.info(
            f"Parsed playlist '{playlist_name}': "
            f"Genre={genre_tags}, Party={party_tags}, Set={set_tags}, "
            f"Radio Moafunk={radio_moafunk_tags}, "
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
            "[\U00002190-\U000021ff][\ufe0e\ufe0f]?|"  # arrows (incl. variation)
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
            "[\U00002190-\U000021ff][\ufe0e\ufe0f]?|"  # arrows with variations
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
