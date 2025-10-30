#!/usr/bin/env python3
"""Verify SmartList has correct MyTag ID."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

try:
    from pyrekordbox import db6
except ImportError:
    print("pyrekordbox not available")
    sys.exit(1)

config = get_config()
service = RekordboxService(config)

# Find House Progressive playlist
playlist = (
    service.db.query(db6.DjmdPlaylist)
    .filter(db6.DjmdPlaylist.Name == "House Progressive")
    .first()
)

if playlist:
    print(f"Playlist: {playlist.Name}")
    print(f"SmartList XML:")
    print(playlist.SmartList)
    print()

    # Get the House Progressive MyTag
    mytag = (
        service.db.query(db6.DjmdMyTag)
        .filter(db6.DjmdMyTag.Name == "House Progressive", db6.DjmdMyTag.Attribute == 0)
        .first()
    )

    if mytag:
        print(f"MyTag ID: {mytag.ID}")
        print(f"Expected ValueLeft in XML: {mytag.ID}")

        # Check if positive ID is in the SmartList
        if str(mytag.ID) in playlist.SmartList:
            print("✅ POSITIVE MyTag ID found in SmartList - CORRECT!")
        elif str(-mytag.ID) in playlist.SmartList:
            print("❌ NEGATIVE MyTag ID found in SmartList - INCORRECT!")
        else:
            print("⚠️  MyTag ID not found in SmartList")
else:
    print("House Progressive playlist not found")

service.close()
