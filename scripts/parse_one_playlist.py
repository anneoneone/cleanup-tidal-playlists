#!/usr/bin/env python3
"""Parse a single playlist name and print expected MyTag values."""
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: parse_one_playlist.py 'Playlist Name'")
    sys.exit(1)

playlist_name = sys.argv[1]

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser

config_path = Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
parser = PlaylistNameParser(config_path)

metadata = parser.parse_playlist_name(playlist_name)
print(f"Playlist: {playlist_name}")
print(f"Clean name: {metadata.playlist_name}")
print("Expected tags:")
for group, tags in metadata.all_tags.items():
    for t in tags:
        print(f"  - {group}::{t}")
