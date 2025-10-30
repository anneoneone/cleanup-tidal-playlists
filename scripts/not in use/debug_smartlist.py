#!/usr/bin/env python3
"""Debug script to inspect SmartList conditions."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

try:
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    db6 = None


def inspect_smartlists():
    """Inspect intelligent playlists and their conditions."""
    if not PYREKORDBOX_AVAILABLE:
        print("❌ pyrekordbox is not available")
        sys.exit(1)

    config = get_config()
    service = RekordboxService(config)

    if not service.db:
        print("❌ Could not connect to Rekordbox database")
        sys.exit(1)

    try:
        # Get all smart playlists (Attribute=4 or those with SmartList)
        all_playlists = service.db.query(db6.DjmdPlaylist).all()
        smart_playlists = [p for p in all_playlists if p.SmartList]

        print(f"Found {len(smart_playlists)} smart playlists\n")

        for playlist in smart_playlists[:5]:  # Just check first 5
            print(f"=" * 80)
            print(f"Playlist: {playlist.Name}")
            print(f"ID: {playlist.ID}")
            print(f"Attribute: {playlist.Attribute}")
            print(f"\nSmartList XML:")
            print(playlist.SmartList)

            # Parse XML to check conditions
            try:
                root = ET.fromstring(playlist.SmartList)
                print(f"\nParsed structure:")
                print(f"  Root tag: {root.tag}")
                print(f"  Root attribs: {root.attrib}")

                # Look for CONDITION nodes
                for condition in root.iter("CONDITION"):
                    print(f"\n  CONDITION found:")
                    print(f"    Attribs: {condition.attrib}")

                    # Check for Property attribute
                    prop = condition.get("Property")
                    operator = condition.get("Operator")
                    value_left = condition.get("ValueLeft")
                    value_right = condition.get("ValueRight")

                    print(f"    Property: {prop}")
                    print(f"    Operator: {operator}")
                    print(f"    ValueLeft: {value_left}")
                    print(f"    ValueRight: {value_right}")

            except ET.ParseError as e:
                print(f"\n  ⚠️  XML parse error: {e}")

            print()

        # Also check MyTags
        print("\n" + "=" * 80)
        print("MYTAG GROUPS AND VALUES")
        print("=" * 80)

        groups = (
            service.db.query(db6.DjmdMyTag).filter(db6.DjmdMyTag.Attribute == 1).all()
        )

        for group in groups:
            print(f"\nGroup: {group.Name} (ID: {group.ID})")

            values = (
                service.db.query(db6.DjmdMyTag)
                .filter(
                    db6.DjmdMyTag.Attribute == 0, db6.DjmdMyTag.ParentID == group.ID
                )
                .all()
            )

            for value in values[:3]:  # Just first 3
                print(f"  - {value.Name} (ID: {value.ID})")

    finally:
        service.close()


if __name__ == "__main__":
    inspect_smartlists()
