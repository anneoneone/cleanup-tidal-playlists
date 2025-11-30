#!/usr/bin/env python3
"""Debug script to check what _extract_emojis returns."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser


def debug_extract_emojis():
    """Debug emoji extraction."""

    # Get config path
    config_path = (
        Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
    )
    parser = PlaylistNameParser(config_path)

    test_string = "Test Playlist 🏃🏼‍♂️ ↗️"
    print(f"Input string: '{test_string}'\n")

    # Test string bytes
    for char in test_string:
        if ord(char) > 127:  # non-ASCII
            codepoints = f"U+{ord(char):04X}"
            print(f"  '{char}' = {codepoints}")

    print("\nExtracted emojis:")
    emojis = parser._extract_emojis(test_string)
    for i, emoji in enumerate(emojis):
        codepoints = " ".join(f"U+{ord(c):04X}" for c in emoji)
        bytes_repr = emoji.encode("utf-8").hex(" ")
        print(f"  {i+1}. '{emoji}'")
        print(f"     Codepoints: {codepoints}")
        print(f"     Bytes: {bytes_repr}")
        print()


if __name__ == "__main__":
    debug_extract_emojis()
