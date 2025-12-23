#!/usr/bin/env python3
"""Test to verify Energy tags in playlist parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser


def test_energy_parsing():
    """Test that Energy tags are properly parsed."""

    config_path = (
        Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
    )
    parser = PlaylistNameParser(config_path)

    # Test case: "House House Up ☀️↗️💾"
    # Should parse to: Genre="House House", Energy="Up", Status="Archived"
    playlist_name = "House House Up ☀️↗️💾"

    print(f"Testing playlist: '{playlist_name}'\n")

    result = parser.parse_playlist_name(playlist_name)

    print(f"Clean name: {result.playlist_name}")
    print(f"Genre tags: {result.genre_tags}")
    print(f"Energy tags: {result.energy_tags}")
    print(f"Status tags: {result.status_tags}")
    print()

    # Verify
    assert "House House" in result.genre_tags, "Genre tag not found!"
    assert "Up" in result.energy_tags, "Energy tag not found!"
    assert "Archived" in result.status_tags, "Status tag not found!"

    print("✅ All tags parsed correctly!")
    print()
    print("Note: Energy tags ARE being parsed and will be applied to tracks")
    print("      as MyTags, but intelligent playlists are NOT created")
    print("      based on Energy tags currently.")


if __name__ == "__main__":
    test_energy_parsing()
