#!/usr/bin/env python3
"""Test script for emoji parsing improvements."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser


def test_emoji_parsing():
    """Test emoji parsing with skin tones and variation selectors."""

    # Get config path
    config_path = (
        Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
    )
    parser = PlaylistNameParser(config_path)

    # Test cases
    # Format: (name, expected_genre/party, expected_energy, expected_status)
    test_cases = [
        ("Test Playlist 🏃🏼‍♂️ ↗️", "House Progressive", "Up", None),
        ("Test Playlist 👵🏻 ↗️", None, "Up", "Old"),
        ("Test Playlist ☀️ ⬆️", "House House", "High", None),
        ("Test Playlist 🎹 ➡️ 💾", "Disco Synth", "Medium", "Archived"),
        # For Party events, the tag value is the playlist name itself
        ("Test Playlist 🎉 ↘️", "Test Playlist", "Low", None),
    ]

    print("Testing emoji parsing:\n")

    for playlist_name, expected_genre, expected_energy, expected_status in test_cases:
        result = parser.parse_playlist_name(playlist_name)

        # Get the actual genre/party value from tags
        actual_genre = None
        if result.genre_tags:
            actual_genre = list(result.genre_tags)[0]
        elif result.party_tags:
            actual_genre = list(result.party_tags)[0]

        actual_energy = list(result.energy_tags)[0] if result.energy_tags else None
        actual_status = list(result.status_tags)[0] if result.status_tags else None

        # Check results
        genre_match = actual_genre == expected_genre
        energy_match = actual_energy == expected_energy
        status_match = actual_status == expected_status

        status_icon = "✅" if (genre_match and energy_match and status_match) else "❌"

        print(f"{status_icon} '{playlist_name}'")
        genre_check = "✓" if genre_match else "✗"
        print(
            f"   Genre/Party: {actual_genre} "
            f"(expected: {expected_genre}) {genre_check}"
        )
        energy_check = "✓" if energy_match else "✗"
        print(
            f"   Energy: {actual_energy} "
            f"(expected: {expected_energy}) {energy_check}"
        )
        status_check = "✓" if status_match else "✗"
        print(
            f"   Status: {actual_status} "
            f"(expected: {expected_status}) {status_check}"
        )
        print()


if __name__ == "__main__":
    test_emoji_parsing()
