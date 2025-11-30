#!/usr/bin/env python3
"""Debug party emoji parsing."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser


def debug_party_emoji():
    """Debug party emoji extraction and parsing."""

    # Get config path
    config_path = (
        Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
    )
    parser = PlaylistNameParser(config_path)

    test_string = "Test Playlist 🎉 ↘️"
    print(f"Input string: '{test_string}'\n")

    print("Extracted emojis:")
    emojis = parser._extract_emojis(test_string)
    for i, emoji in enumerate(emojis):
        codepoints = " ".join(f"U+{ord(c):04X}" for c in emoji)
        print(f"  {i+1}. '{emoji}' = {codepoints}")

    print("\nParsing result:")
    result = parser.parse_playlist_name(test_string)
    print(f"  Party tags: {result.party_tags}")
    print(f"  Energy tags: {result.energy_tags}")
    print(f"  Raw name: {result.raw_name}")
    print(f"  Clean name: {parser._extract_clean_name(test_string)}")


if __name__ == "__main__":
    debug_party_emoji()
