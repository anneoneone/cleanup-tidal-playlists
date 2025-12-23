#!/usr/bin/env python3
"""Check logical operators across multiple playlists."""

from pyrekordbox.db6 import DjmdPlaylist
from pyrekordbox.db6.smartlist import SmartList

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    # Get several intelligent playlists
    playlists = (
        service.db.query(DjmdPlaylist)
        .filter(DjmdPlaylist.Attribute == 4, DjmdPlaylist.SmartList.isnot(None))
        .limit(20)
        .all()
    )

    print("Checking logical operators:\n")

    for playlist in playlists:
        smart_list = SmartList()
        smart_list.parse(playlist.SmartList)

        # Count MyTag conditions
        mytag_count = sum(
            1
            for c in smart_list.conditions
            if hasattr(c, "property") and c.property == "myTag"
        )

        print(f"{playlist.Name}")
        print(
            f"  LogicalOperator: {smart_list.logical_operator} ({'AND' if smart_list.logical_operator == 0 else 'OR'})"
        )
        print(f"  MyTag conditions: {mytag_count}")
        print()
else:
    print("❌ Database not available")
