#!/usr/bin/env python3
"""Check the property attribute value."""

from pyrekordbox.db6 import DjmdPlaylist
from pyrekordbox.db6.smartlist import SmartList

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    playlist = (
        service.db.query(DjmdPlaylist)
        .filter(DjmdPlaylist.Attribute == 4, DjmdPlaylist.SmartList.isnot(None))
        .first()
    )

    if playlist:
        print(f"Testing playlist: {playlist.Name}")

        smart_list = SmartList()
        smart_list.parse(playlist.SmartList)

        for i, condition in enumerate(smart_list.conditions):
            print(f"\nCondition {i}:")
            print(f"  property: {condition.property}")
            print(f"  property type: {type(condition.property)}")
            print(f"  value_left: {condition.value_left}")
            print(f"  operator: {condition.operator}")
