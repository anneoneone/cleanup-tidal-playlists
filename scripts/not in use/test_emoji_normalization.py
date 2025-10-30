#!/usr/bin/env python3
"""Test emoji normalization."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser

# Initialize parser
config_path = Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
parser = PlaylistNameParser(config_path)

print("Testing emoji normalization:\n")
print("=" * 80)

# Test emojis with skin tones
test_emojis = [
    ("🏃🏼‍♂️", "House Progressive (with skin tone)"),
    ("🏃", "House Progressive (base)"),
    ("🧘🏼‍♂️", "House Chill (with skin tone)"),
    ("🧘", "House Chill (base)"),
    ("👵🏻", "Old (with skin tone)"),
    ("👵", "Old (base)"),
]

print("\nEmoji normalization results:")
for emoji, description in test_emojis:
    normalized = parser._normalize_emoji(emoji)
    lookup = parser.emoji_to_group_tag.get(normalized)

    print(f"\n{description}:")
    print(f"  Original: '{emoji}' (len={len(emoji)})")
    print(f"  Normalized: '{normalized}' (len={len(normalized)})")

    if lookup:
        group, tag_name = lookup
        print(f"  ✓ Found: {group}/{tag_name}")
    else:
        print(f"  ✗ Not found in mapping")

print("\n" + "=" * 80)
print("\nAll normalized emojis in mapping:")
print("=" * 80)
for norm_emoji, (group, tag) in sorted(parser.emoji_to_group_tag.items()):
    print(f"'{norm_emoji}' -> {group}/{tag}")
