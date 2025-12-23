#!/usr/bin/env python3
"""Manually check some playlists to verify they have tracks."""

from pyrekordbox.db6 import DjmdContent, DjmdPlaylist, DjmdSongMyTag
from pyrekordbox.db6.smartlist import SmartList

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    # Get some intelligent playlists
    playlists = (
        service.db.query(DjmdPlaylist)
        .filter(DjmdPlaylist.Attribute == 4, DjmdPlaylist.SmartList.isnot(None))
        .limit(10)
        .all()
    )

    print(f"Checking {len(playlists)} intelligent playlists:\n")

    for playlist in playlists:
        print(f"\n{'='*70}")
        print(f"Playlist: {playlist.Name}")

        # Parse SmartList
        smart_list = SmartList()
        smart_list.parse(playlist.SmartList)

        # Get MyTag IDs
        mytag_ids = []
        for condition in smart_list.conditions:
            if hasattr(condition, "property") and condition.property == "myTag":
                if hasattr(condition, "value_left") and condition.value_left:
                    mytag_ids.append(int(condition.value_left))

        print(f"MyTag IDs: {mytag_ids}")
        print(
            f"Logical Operator: {'AND' if smart_list.logical_operator == 0 else 'OR'}"
        )

        # Check track count for each MyTag
        for mytag_id in mytag_ids:
            count = (
                service.db.query(DjmdSongMyTag)
                .filter(DjmdSongMyTag.MyTagID == str(mytag_id))
                .count()
            )
            print(f"  MyTag {mytag_id}: {count} tracks")

        # Check using the service method
        is_empty = service._is_intelligent_playlist_empty(playlist)
        print(f"\nService says: {'EMPTY' if is_empty else 'NOT EMPTY'}")

        # Let's also check actual track count in the database for this playlist
        # Get track IDs that should be in this playlist
        if mytag_ids and smart_list.logical_operator == 1:  # OR
            actual_track_count = (
                service.db.query(DjmdSongMyTag)
                .filter(DjmdSongMyTag.MyTagID.in_([str(id) for id in mytag_ids]))
                .count()
            )
            print(f"Actual tracks matching conditions: {actual_track_count}")
else:
    print("❌ Database not available")
