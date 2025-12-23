#!/usr/bin/env python3
"""Test script to verify event playlist handling.

This script tests:
1. Event playlist detection from emojis (🎉, 🎶, 🎙️)
2. Creation of Event MyTags (Event::Party::event_name)
3. Creation of intelligent playlists under Events/{type}/event_name
4. Tagging of all tracks in the event playlist
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database

from tidal_cleanup.services.track_tag_sync_service import TrackTagSyncService

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def print_event_structure(db, events_folder_id):
    """Print the Events folder structure."""
    from pyrekordbox import db6

    print("\n" + "=" * 70)
    print("Events Folder Structure:")
    print("=" * 70)

    # Get event type folders (Partys, Sets, Radio Moafunk)
    type_folders = (
        db.query(db6.DjmdPlaylist)
        .filter(
            (db6.DjmdPlaylist.ParentID == events_folder_id)
            & (db6.DjmdPlaylist.Attribute == 1)
        )
        .all()
    )

    for type_folder in type_folders:
        print(f"\n📁 {type_folder.Name}")

        # Get intelligent playlists under this type
        playlists = (
            db.query(db6.DjmdPlaylist)
            .filter(
                (db6.DjmdPlaylist.ParentID == type_folder.ID)
                & (db6.DjmdPlaylist.Attribute == 4)
            )
            .all()
        )

        for playlist in playlists:
            print(f"  🎵 {playlist.Name} (Smart Playlist, ID: {playlist.ID})")

    print("=" * 70 + "\n")


def print_event_tags(db):
    """Print all event-related MyTags."""
    from pyrekordbox import db6

    print("\n" + "=" * 70)
    print("Event MyTags:")
    print("=" * 70)

    # Query MyTags for each event type category
    event_categories = ["Party", "Set", "Radio Moafunk"]

    total_tags = 0
    for category in event_categories:
        # Find the MyTag group for this category
        tag_list = (
            db.query(db6.DjmdMyTag)
            .join(
                db6.DjmdMyTag.my_tag,
            )
            .filter(db6.DjmdMyTag.my_tag.has(Name=category))
            .all()
        )

        if tag_list:
            print(f"\n📁 {category}:")
            for tag in tag_list:
                print(f"  🏷️  {tag.Name}")
            total_tags += len(tag_list)
        else:
            print(f"\n📁 {category}: (no tags)")

    print(f"\nTotal event tags: {total_tags}")
    print("=" * 70 + "\n")


def main():
    """Run the test."""
    # Paths
    rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"
    mp3_playlists_root = (
        Path.home() / "Music/iTunes/iTunes Media/Automatically Add to Music.localized"
    )
    mytag_mapping_path = (
        Path(__file__).parent.parent / "config/rekordbox_mytag_mapping.json"
    )

    # Use a test directory if the default doesn't exist
    if not mp3_playlists_root.exists():
        mp3_playlists_root = Path(__file__).parent.parent / "test_playlists"
        print(f"Using test directory: {mp3_playlists_root}")

    if not rekordbox_db.exists():
        print(f"❌ Rekordbox database not found: {rekordbox_db}")
        return 1

    if not mytag_mapping_path.exists():
        print(f"❌ MyTag mapping not found: {mytag_mapping_path}")
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

        # Test parsing event playlist names
        print("=" * 70)
        print("Testing Event Playlist Name Parsing:")
        print("=" * 70)

        test_names = [
            "23-04-04 carlparty selection 🎉",
            "Summer Vibes Set 🎶⬆️",
            "Radio Moafunk Episode 1 🎙️",
            "House Party Mix 🎉⚡",
        ]

        for name in test_names:
            metadata = service.name_parser.parse_playlist_name(name)
            print(f"\nPlaylist: {name}")
            print(f"  Clean name: {metadata.playlist_name}")
            print(f"  Party tags: {metadata.party_tags}")
            print(f"  Is event: {service._is_event_playlist(metadata)}")
            if service._is_event_playlist(metadata):
                event_type = service._get_event_type(metadata)
                print(f"  Event type: {event_type}")

        # Find Events folder
        from pyrekordbox import db6

        events_folder = (
            db.query(db6.DjmdPlaylist)
            .filter(db6.DjmdPlaylist.Name == "Events", db6.DjmdPlaylist.Attribute == 1)
            .first()
        )

        if events_folder:
            print("\n📊 Current Event Structure:")
            print_event_structure(db, events_folder.ID)
            print_event_tags(db)
        else:
            print("\n⚠️  No Events folder found (run Step 1 first)")

        print("\n✅ Event playlist test completed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
