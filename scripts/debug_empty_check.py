#!/usr/bin/env python3
"""Debug script to test intelligent playlist empty checking."""

from pyrekordbox.db6 import DjmdPlaylist

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    # Get all playlists
    all_playlists = service.db.query(DjmdPlaylist).all()

    # Find an intelligent playlist with SmartList
    print("Looking for intelligent playlists...")
    count = 0
    for p in all_playlists:
        if p.Attribute == 4 and p.SmartList:
            count += 1
            if count <= 3:  # Test first 3
                print(f"\n{'='*60}")
                print(f"Testing playlist: {p.Name}")
                print(f"Attribute: {p.Attribute}")
                print(f"Has SmartList: {bool(p.SmartList)}")
                print(f"SmartList content (first 300 chars):\n{p.SmartList[:300]}")

                # Test if it's empty
                is_empty = service._is_intelligent_playlist_empty(p)
                print(f"\nResult: Is empty = {is_empty}")

                # Check songs
                print(f"Number of explicit songs: {len(p.Songs)}")

    print(f"\n\nTotal intelligent playlists found: {count}")
else:
    print("❌ Database not available")
