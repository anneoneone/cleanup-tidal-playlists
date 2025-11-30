#!/usr/bin/env python3
"""Debug script to check emoji mapping."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser


def debug_emoji_mapping():
    """Debug emoji mapping to see what's stored."""

    # Get config path
    config_path = (
        Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
    )
    parser = PlaylistNameParser(config_path)

    print("Energy emojis in reverse mapping:\n")
    for emoji, (group, tag) in parser.emoji_to_group_tag.items():
        if group == "Energy":
            codepoints = " ".join(f"U+{ord(c):04X}" for c in emoji)
            bytes_repr = emoji.encode("utf-8").hex(" ")
            print(f"  '{emoji}' -> {tag}")
            print(f"    Codepoints: {codepoints}")
            print(f"    Bytes: {bytes_repr}")
            print()

    print("\nTest parsing '↗️' from playlist name:")
    test_emoji = "↗️"
    codepoints = " ".join(f"U+{ord(c):04X}" for c in test_emoji)
    bytes_repr = test_emoji.encode("utf-8").hex(" ")
    print(f"  Input emoji: '{test_emoji}'")
    print(f"    Codepoints: {codepoints}")
    print(f"    Bytes: {bytes_repr}")

    # Try normalizing with and without variation selector
    normalized_with = parser._normalize_emoji(
        test_emoji, preserve_variation_selector=True
    )
    normalized_without = parser._normalize_emoji(
        test_emoji, preserve_variation_selector=False
    )

    print(f"\n  Normalized WITH variation selector: '{normalized_with}'")
    codepoints_with = " ".join(f"U+{ord(c):04X}" for c in normalized_with)
    print(f"    Codepoints: {codepoints_with}")
    print(f"    In mapping: {normalized_with in parser.emoji_to_group_tag}")

    print(f"\n  Normalized WITHOUT variation selector: '{normalized_without}'")
    codepoints_without = " ".join(f"U+{ord(c):04X}" for c in normalized_without)
    print(f"    Codepoints: {codepoints_without}")
    in_mapping = normalized_without in parser.emoji_to_group_tag
    print(f"    In mapping: {in_mapping}")


if __name__ == "__main__":
    debug_emoji_mapping()
