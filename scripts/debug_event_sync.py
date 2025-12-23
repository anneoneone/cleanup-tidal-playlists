#!/usr/bin/env python3
"""Debug script to test event playlist sync directly."""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database

from tidal_cleanup.services.track_tag_sync_service import TrackTagSyncService

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Test event sync."""
    # Paths
    rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"
    mp3_playlists_root = Path.home() / "Music/mp3-playlists"
    mytag_mapping_path = (
        Path(__file__).parent.parent / "config/rekordbox_mytag_mapping.json"
    )

    if not rekordbox_db.exists():
        print(f"❌ Rekordbox database not found: {rekordbox_db}")
        return 1

    if not mp3_playlists_root.exists():
        print(f"❌ MP3 playlists root not found: {mp3_playlists_root}")
        print("Please specify the correct path to your MP3 playlists")
        return 1

    print("🔧 Opening Rekordbox database...")
    with Rekordbox6Database(rekordbox_db) as db:
        print("✓ Database opened successfully\n")

        # Create service
        service = TrackTagSyncService(
            db=db,
            mp3_playlists_root=mp3_playlists_root,
            mytag_mapping_path=mytag_mapping_path,
        )

        # List all playlists
        print("=" * 70)
        print("Available playlists:")
        print("=" * 70)

        playlist_dirs = [d for d in mp3_playlists_root.iterdir() if d.is_dir()]

        for i, playlist_dir in enumerate(playlist_dirs, 1):
            metadata = service.name_parser.parse_playlist_name(playlist_dir.name)
            is_event = service._is_event_playlist(metadata)
            event_type = service._get_event_type(metadata) if is_event else "N/A"

            print(f"{i:3d}. {playlist_dir.name}")
            print(f"     Event: {is_event}, Type: {event_type}")
            print(f"     Party tags: {metadata.party_tags}")
            print()

        # Ask user to select one
        print("=" * 70)
        choice = input("\nEnter playlist number to sync (or 'q' to quit): ").strip()

        if choice.lower() == "q":
            return 0

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(playlist_dirs):
                playlist_name = playlist_dirs[idx].name

                print(f"\n🔄 Syncing playlist: {playlist_name}")
                print("=" * 70)

                result = service.sync_playlist(playlist_name)

                print("\n✅ Sync completed!")
                print(f"Result: {result}")

            else:
                print("❌ Invalid selection")
        except ValueError:
            print("❌ Invalid input")

    return 0


if __name__ == "__main__":
    sys.exit(main())
