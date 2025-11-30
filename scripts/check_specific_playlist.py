#!/usr/bin/env python3
"""Check specific playlist in detail."""

from pyrekordbox.db6 import DjmdPlaylist, DjmdSongMyTag
from pyrekordbox.db6.smartlist import SmartList

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    # Find the specific playlist
    playlist = (
        service.db.query(DjmdPlaylist)
        .filter(DjmdPlaylist.Name == "🥊 House Ghetto ↘️")
        .first()
    )

    if not playlist:
        print("Playlist not found!")
    else:
        print(f"Playlist: {playlist.Name}")
        print(f"Attribute: {playlist.Attribute}")
        print(f"Number of explicit Songs: {len(playlist.Songs)}")
        print(f"\nSmartList XML:")
        print(playlist.SmartList)

        # Parse SmartList
        smart_list = SmartList()
        smart_list.parse(playlist.SmartList)

        print(
            f"\nLogical Operator: {smart_list.logical_operator} ({'AND' if smart_list.logical_operator == 0 else 'OR'})"
        )
        print(f"Number of conditions: {len(smart_list.conditions)}")

        # Check each condition
        print("\nConditions:")
        for i, condition in enumerate(smart_list.conditions):
            print(f"\n  Condition {i+1}:")
            print(f"    Property: {condition.property}")
            print(f"    Operator: {condition.operator}")
            print(f"    Value Left: {condition.value_left}")
            print(f"    Value Right: {condition.value_right}")

            if condition.property == "myTag":
                mytag_id = int(condition.value_left)
                count = (
                    service.db.query(DjmdSongMyTag)
                    .filter(DjmdSongMyTag.MyTagID == str(mytag_id))
                    .count()
                )
                print(f"    → Tracks with this MyTag: {count}")

        # Check what the algorithm says
        is_empty = service._is_intelligent_playlist_empty(playlist)
        print(f"\n{'='*70}")
        print(f"Algorithm result: {'EMPTY' if is_empty else 'NOT EMPTY'}")

        # For OR logic, check if ANY track has ANY of the MyTags
        if smart_list.logical_operator == 1:
            mytag_ids = []
            for condition in smart_list.conditions:
                if condition.property == "myTag" and condition.value_left:
                    mytag_ids.append(int(condition.value_left))

            print(
                f"\nOR Logic - checking if ANY track has ANY of these MyTags: {mytag_ids}"
            )

            for mytag_id in mytag_ids:
                sample_tracks = (
                    service.db.query(DjmdSongMyTag)
                    .filter(DjmdSongMyTag.MyTagID == str(mytag_id))
                    .limit(3)
                    .all()
                )

                if sample_tracks:
                    print(
                        f"\n  MyTag {mytag_id} - Found {len(sample_tracks)} sample tracks:"
                    )
                    for track in sample_tracks:
                        print(f"    - Track ID: {track.ID}")
else:
    print("❌ Database not available")
