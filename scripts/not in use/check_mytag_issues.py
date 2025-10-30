#!/usr/bin/env python3
"""Check for MyTag issues with problematic genres."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

# Get Genre group
genre_group = (
    service.db.query(db6.DjmdMyTag)
    .filter(db6.DjmdMyTag.Name == "Genre", db6.DjmdMyTag.Attribute == 1)
    .first()
)

if genre_group:
    # Check for problematic genres
    problem_genres = ["House Progressive", "House Chill", "Old", "Beach"]

    print("Checking MyTags for genres with emoji skin tones:\n")
    for genre_name in problem_genres:
        mytag = (
            service.db.query(db6.DjmdMyTag)
            .filter(
                db6.DjmdMyTag.Name == genre_name,
                db6.DjmdMyTag.Attribute == 0,
                db6.DjmdMyTag.ParentID == genre_group.ID,
            )
            .first()
        )

        if mytag:
            print(f"✓ {genre_name}: ID={mytag.ID}")

            # Check if playlist exists
            playlist = (
                service.db.query(db6.DjmdPlaylist)
                .filter(db6.DjmdPlaylist.Name == genre_name)
                .first()
            )

            if playlist:
                print(f"  Playlist ID: {playlist.ID}")
                print(f"  SmartList: {playlist.SmartList[:100]}...")
        else:
            print(f"✗ {genre_name}: NOT FOUND")

    print("\n" + "=" * 80)
    print("All Genre MyTags:")
    print("=" * 80)
    all_tags = (
        service.db.query(db6.DjmdMyTag)
        .filter(db6.DjmdMyTag.Attribute == 0, db6.DjmdMyTag.ParentID == genre_group.ID)
        .order_by(db6.DjmdMyTag.Name)
        .all()
    )

    for tag in all_tags:
        print(f"  - {tag.Name} (ID: {tag.ID})")

service.close()
