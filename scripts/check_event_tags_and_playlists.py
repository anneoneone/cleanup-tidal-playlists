#!/usr/bin/env python3
"""Check which event tags exist and which have intelligent playlists."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database, db6


def main():
    """Check event tags and their playlists."""
    rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"

    print("🔧 Opening Rekordbox database...")
    db = Rekordbox6Database(rekordbox_db)
    print("✓ Database opened successfully\n")

    # Event type groups
    event_groups = ["Party", "Set", "Radio Moafunk"]

    for group_name in event_groups:
        print(f"\n{'='*70}")
        print(f"MyTag Group: {group_name}")
        print("=" * 70)

        # Find the group
        group = db.get_my_tag(Name=group_name).first()
        if not group:
            print(f"  ⚠️  MyTag group '{group_name}' does not exist")
            continue

        print(f"  ✓ Group exists (ID: {group.ID})")

        # Find all tags in this group
        tags = db.query(db6.DjmdMyTag).filter(db6.DjmdMyTag.ParentID == group.ID).all()

        if not tags:
            print(f"  ℹ️  No tags found in this group")
            continue

        print(f"  Found {len(tags)} tag(s):\n")

        # Map folder names
        event_folder_map = {
            "Party": "Partys",
            "Set": "Sets",
            "Radio Moafunk": "Radio Moafunk",
        }
        folder_name = event_folder_map.get(group_name, group_name)

        # Get the Events folder and type folder
        events_folder = db.get_playlist(Name="Events", Attribute=1).first()
        if not events_folder:
            print("  ⚠️  'Events' folder does not exist")
            continue

        type_folder = db.get_playlist(
            Name=folder_name, ParentID=events_folder.ID, Attribute=1
        ).first()
        if not type_folder:
            print(f"  ⚠️  '{folder_name}' folder does not exist under Events")
            continue

        # Check each tag
        for tag in tags:
            tag_name = tag.Name

            # Check if intelligent playlist exists
            playlist = db.get_playlist(
                Name=tag_name,
                ParentID=type_folder.ID,
                Attribute=4,  # 4 = intelligent playlist
            )

            status = "✓ Has playlist" if playlist else "✗ Missing playlist"
            print(f"    • {tag_name:50} {status}")

    print(f"\n{'='*70}\n")
    db.close()


if __name__ == "__main__":
    sys.exit(main())
