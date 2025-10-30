#!/usr/bin/env python3
"""Find playlists matching a pattern."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

search_term = "House Progressive"

print(f"Searching for playlists containing '{search_term}'...\n")

# Get all playlists, not just smart ones
playlists = (
    service.db.query(db6.DjmdPlaylist)
    .filter(
        db6.DjmdPlaylist.Name.like(f"%{search_term}%"),
        db6.DjmdPlaylist.Attribute.in_([0, 4]),  # Regular and smart playlists
    )
    .all()
)

if playlists:
    print(f"Found {len(playlists)} playlists:\n")
    for pl in playlists:
        pl_type = "Folder" if pl.Attribute == 1 else "Playlist"
        if pl.Attribute == 4:
            pl_type = "Smart Playlist"

        print(f"  {pl_type}: {pl.Name}")
        print(f"    ID: {pl.ID}")
        print(f"    Attribute: {pl.Attribute}")

        if pl.Attribute == 0:  # Regular playlist
            track_count = len(pl.Songs) if pl.Songs else 0
            print(f"    Tracks: {track_count}")

        print()
else:
    print(f"No playlists found containing '{search_term}'")

service.close()
