#!/usr/bin/env python3
"""Test parsing playlist names with emoji modifiers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser

# Initialize parser
config_path = Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
parser = PlaylistNameParser(config_path)

print("Testing playlist name parsing with emoji modifiers:\n")
print("=" * 80)

# Test playlist names with emojis that have skin tone modifiers
test_playlists = [
    "Cool Mix 🏃🏼‍♂️ ➡️",  # House Progressive + Medium energy
    "Chill Vibes 🧘🏼‍♂️ ↘️",  # House Chill + Low energy
    "Old School 🎷 👵🏻",  # Jazz + Old status
    "Beach Party 🏖️ ⬆️",  # Beach + High energy
]

for playlist_name in test_playlists:
    print(f"\nPlaylist: {playlist_name}")
    metadata = parser.parse_playlist_name(playlist_name)

    print(f"  Clean name: {metadata.playlist_name}")
    print(f"  Genre tags: {metadata.genre_tags}")
    print(f"  Energy tags: {metadata.energy_tags}")
    print(f"  Status tags: {metadata.status_tags}")

    if metadata.has_genre_or_party:
        print("  ✓ Has genre or party tag")
    else:
        print("  ✗ Missing genre or party tag")

print("\n" + "=" * 80)
