#!/usr/bin/env python3
"""Diagnose track tagging issues - show which tracks are missing expected tags."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

# Initialize parser
config_path = Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
parser = PlaylistNameParser(config_path)

print("=" * 80)
print("TRACK TAGGING DIAGNOSIS")
print("=" * 80)

# Test with a specific playlist that has emoji modifiers
test_playlists = [
    "Cool Mix 🏃🏼‍♂️ ➡️",  # Adjust to actual playlist names in your DB
    # Add more playlist names here
]

# Or find all playlists with emoji modifiers
print("\nSearching for playlists with emoji skin tone modifiers...\n")

all_playlists = (
    service.db.query(db6.DjmdPlaylist)
    .filter(db6.DjmdPlaylist.Attribute == 0)  # Regular playlists
    .all()
)

emoji_modifiers = ["🏃🏼‍♂️", "🧘🏼‍♂️", "👵🏻", "🏖️"]
problem_playlists = []

for playlist in all_playlists:
    for emoji in emoji_modifiers:
        if emoji in playlist.Name:
            problem_playlists.append(playlist)
            break

if problem_playlists:
    print(f"Found {len(problem_playlists)} playlists with emoji modifiers:")
    for pl in problem_playlists[:10]:  # Show first 10
        print(f"\n📋 Playlist: {pl.Name}")

        # Parse what tags SHOULD be applied
        metadata = parser.parse_playlist_name(pl.Name)
        expected_tags = []
        for group, tags in metadata.all_tags.items():
            for tag in tags:
                expected_tags.append(f"{group}::{tag}")

        print(
            f"   Expected tags: {', '.join(expected_tags) if expected_tags else 'None'}"
        )

        # Check first track
        if pl.Songs:
            first_song = pl.Songs[0]
            content = first_song.Content

            # Get actual tags on track
            tag_links = (
                service.db.query(db6.DjmdSongMyTag)
                .filter(db6.DjmdSongMyTag.ContentID == content.ID)
                .all()
            )

            actual_tags = []
            for link in tag_links:
                tag = (
                    service.db.query(db6.DjmdMyTag)
                    .filter(
                        db6.DjmdMyTag.ID == link.MyTagID, db6.DjmdMyTag.Attribute == 0
                    )
                    .first()
                )

                if tag:
                    # Get group
                    group = (
                        service.db.query(db6.DjmdMyTag)
                        .filter(
                            db6.DjmdMyTag.ID == tag.ParentID,
                            db6.DjmdMyTag.Attribute == 1,
                        )
                        .first()
                    )

                    if group:
                        actual_tags.append(f"{group.Name}::{tag.Name}")

            print(f"   First track: {content.Title}")
            print(
                f"   Actual tags: {', '.join(actual_tags) if actual_tags else 'None'}"
            )

            # Check if expected tags are present
            missing = [tag for tag in expected_tags if tag not in actual_tags]
            if missing:
                print(f"   ⚠️  Missing tags: {', '.join(missing)}")
            else:
                print(f"   ✓ All expected tags present")
else:
    print("No playlists found with emoji modifiers.")

print("\n" + "=" * 80)
print("SOLUTION:")
print("=" * 80)
print("If tracks are missing tags, re-sync the playlists:")
print("  python -m tidal_cleanup.rekordbox sync 'Playlist Name'")
print("\nThe emoji normalization fix ensures new syncs will work correctly!")

service.close()
