#!/usr/bin/env python3
"""Check SmartList conditions in detail."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

# Check specific playlists with emoji skin tones
problem_playlists = ["House Progressive", "House Chill", "Beach"]

print("Checking SmartList conditions for problematic playlists:\n")
print("=" * 80)

for name in problem_playlists:
    playlist = (
        service.db.query(db6.DjmdPlaylist).filter(db6.DjmdPlaylist.Name == name).first()
    )

    if playlist and playlist.SmartList:
        print(f"\nPlaylist: {name}")
        print(f"SmartList XML:\n{playlist.SmartList}\n")

        # Parse and check
        try:
            root = ET.fromstring(playlist.SmartList)
            for condition in root.iter("CONDITION"):
                print(f"Condition attributes:")
                for key, value in condition.attrib.items():
                    print(f"  {key}: {value}")

                # Check if ValueLeft is empty or None
                value_left = condition.get("ValueLeft")
                if not value_left or value_left == "":
                    print("  ⚠️  WARNING: ValueLeft is empty!")
        except ET.ParseError as e:
            print(f"  Error parsing XML: {e}")

        print("-" * 80)

service.close()
