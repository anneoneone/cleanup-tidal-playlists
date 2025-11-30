#!/usr/bin/env python3
"""Find intelligent playlists that are truly empty."""

from pyrekordbox.db6 import DjmdPlaylist, DjmdSongMyTag
from pyrekordbox.db6.smartlist import SmartList

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    # Get all intelligent playlists
    intelligent_playlists = (
        service.db.query(DjmdPlaylist)
        .filter(DjmdPlaylist.Attribute == 4, DjmdPlaylist.SmartList.isnot(None))
        .all()
    )

    print(f"Total intelligent playlists: {len(intelligent_playlists)}")

    empty_count = 0
    non_empty_count = 0
    error_count = 0
    empty_playlists = []

    for playlist in intelligent_playlists:  # Check ALL
        try:
            # Parse SmartList
            smart_list = SmartList()
            smart_list.parse(playlist.SmartList)

            # Extract MyTag IDs
            mytag_ids = []
            for condition in smart_list.conditions:
                if hasattr(condition, "property") and condition.property == "myTag":
                    if hasattr(condition, "value_left") and condition.value_left:
                        mytag_id = int(condition.value_left)
                        mytag_ids.append(mytag_id)

            if not mytag_ids:
                empty_count += 1
                empty_playlists.append(playlist.Name)
                continue

            # Check if any tracks have these MyTags
            has_tracks = False
            for mytag_id in mytag_ids:
                count = (
                    service.db.query(DjmdSongMyTag)
                    .filter(DjmdSongMyTag.MyTagID == str(mytag_id))
                    .count()
                )

                if count > 0:
                    has_tracks = True
                    break

            if has_tracks:
                non_empty_count += 1
            else:
                empty_count += 1
                empty_playlists.append(playlist.Name)

        except Exception as e:
            error_count += 1

    print(f"\n\nSummary (all {len(intelligent_playlists)} playlists):")
    print(f"  Empty: {empty_count}")
    print(f"  Non-empty: {non_empty_count}")
    print(f"  Errors: {error_count}")

    if empty_playlists:
        print(f"\nFirst 10 empty intelligent playlists:")
        for name in empty_playlists[:10]:
            print(f"  - {name}")
else:
    print("❌ Database not available")
