#!/usr/bin/env python3
"""Test parsing of specific playlist name."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser

config_path = Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
parser = PlaylistNameParser(config_path)

# Test the actual playlist name
playlist_name = "House Progressive 🏃🏼‍♂️❓"

print("=" * 80)
print(f"Testing playlist: {playlist_name}")
print("=" * 80)

metadata = parser.parse_playlist_name(playlist_name)

print(f"\nClean name: {metadata.playlist_name}")
print(f"\nTags extracted:")
print(f"  Genre tags: {metadata.genre_tags}")
print(f"  Party tags: {metadata.party_tags}")
print(f"  Energy tags: {metadata.energy_tags}")
print(f"  Status tags: {metadata.status_tags}")

# Check the emojis
print(f"\nEmoji analysis:")
emojis = parser._extract_emojis(playlist_name)
print(f"  Found {len(emojis)} emojis: {emojis}")

for i, emoji in enumerate(emojis, 1):
    normalized = parser._normalize_emoji(emoji)
    print(f"\n  Emoji {i}: '{emoji}' (length={len(emoji)})")
    print(f"    Normalized: '{normalized}' (length={len(normalized)})")

    lookup = parser.emoji_to_group_tag.get(normalized)
    if lookup:
        group, tag_name = lookup
        print(f"    ✓ Mapped to: {group}/{tag_name}")
    else:
        print(f"    ✗ Not found in mapping")

print("\n" + "=" * 80)
if metadata.has_genre_or_party:
    print("✓ Has genre or party tag")
else:
    print("✗ Missing genre or party tag")
print("=" * 80)
