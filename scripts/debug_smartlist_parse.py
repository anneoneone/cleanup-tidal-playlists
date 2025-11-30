#!/usr/bin/env python3
"""Debug script to trace through the empty check logic."""

from pyrekordbox.db6 import DjmdPlaylist, DjmdSongMyTag
from pyrekordbox.db6.smartlist import SmartList

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    # Get first intelligent playlist
    playlist = (
        service.db.query(DjmdPlaylist)
        .filter(DjmdPlaylist.Attribute == 4, DjmdPlaylist.SmartList != None)
        .first()
    )

    if playlist:
        print(f"Testing playlist: {playlist.Name}")
        print(f"SmartList XML:\n{playlist.SmartList}\n")

        # Parse SmartList
        smart_list = SmartList()
        smart_list.parse(playlist.SmartList)

        print(f"Number of conditions: {len(smart_list.conditions)}")

        # Check each condition
        mytag_ids = []
        for i, condition in enumerate(smart_list.conditions):
            print(f"\nCondition {i}:")
            print(f"  Has 'prop' attr: {hasattr(condition, 'prop')}")
            if hasattr(condition, "prop"):
                print(f"  prop value: {condition.prop}")
            print(f"  Has 'value_left' attr: {hasattr(condition, 'value_left')}")
            if hasattr(condition, "value_left"):
                print(f"  value_left: {condition.value_left}")

            # Show all attributes
            print(
                f"  All attributes: {[a for a in dir(condition) if not a.startswith('_')]}"
            )

            if hasattr(condition, "prop") and condition.prop == 24:
                if hasattr(condition, "value_left") and condition.value_left:
                    mytag_id = int(condition.value_left)
                    mytag_ids.append(mytag_id)
                    print(f"  ✓ Extracted MyTag ID: {mytag_id}")

        print(f"\n\nExtracted MyTag IDs: {mytag_ids}")

        # Check if tracks exist with these MyTags
        for mytag_id in mytag_ids:
            count = (
                service.db.query(DjmdSongMyTag)
                .filter(DjmdSongMyTag.MyTagID == str(mytag_id))
                .count()
            )
            print(f"  MyTag {mytag_id}: {count} tracks")
    else:
        print("No intelligent playlists found")
else:
    print("❌ Database not available")
