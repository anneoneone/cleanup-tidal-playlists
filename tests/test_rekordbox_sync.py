#!/usr/bin/env python3
"""Test script for the refactored Rekordbox playlist synchronization.

This script tests the new playlist sync functionality with MyTag management. It
demonstrates the complete workflow from parsing playlist names to synchronizing tracks
and managing MyTags.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config  # noqa: E402
from tidal_cleanup.services.rekordbox_service import (  # noqa: E402
    RekordboxService,
)

try:
    from pyrekordbox import Rekordbox6Database  # noqa: E402

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    print("❌ pyrekordbox not available - install with: pip install pyrekordbox")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_playlist_name_parser():
    """Test the playlist name parser."""
    from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser

    logger.info("=" * 60)
    logger.info("Testing Playlist Name Parser")
    logger.info("=" * 60)

    config_path = (
        Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
    )
    parser = PlaylistNameParser(config_path)

    # Test cases
    test_names = [
        "Jazzz D 🎷💾",  # Genre + Status
        "House Party 🎉⚡✅",  # Party + Energy + Status
        "Electronic Mix 🎹🔥",  # Genre + Energy
        "Latin Dance 💃🌟",  # Party + Energy
        "Cool Jazz 🎷❄️🆕",  # Genre + Energy + Status
        "Rock Collection 🎸",  # Genre only
    ]

    for name in test_names:
        logger.info(f"\nParsing: {name}")
        metadata = parser.parse_playlist_name(name)
        logger.info(f"  Clean name: {metadata.playlist_name}")
        logger.info(f"  Genre tags: {metadata.genre_tags}")
        logger.info(f"  Party tags: {metadata.party_tags}")
        logger.info(f"  Energy tags: {metadata.energy_tags}")
        logger.info(f"  Status tags: {metadata.status_tags}")

    logger.info("\n✅ Playlist name parser test completed")


def test_mytag_manager():
    """Test the MyTag manager."""
    from tidal_cleanup.services.mytag_manager import MyTagManager

    logger.info("\n" + "=" * 60)
    logger.info("Testing MyTag Manager")
    logger.info("=" * 60)

    try:
        db = Rekordbox6Database()
        manager = MyTagManager(db)

        # Test creating/getting groups
        logger.info("\nTesting group creation...")
        genre_group = manager.create_or_get_group("Genre")
        logger.info(f"✅ Genre group: {genre_group.Name} (ID: {genre_group.ID})")

        party_group = manager.create_or_get_group("Party")
        logger.info(f"✅ Party group: {party_group.Name} (ID: {party_group.ID})")

        # Test creating/getting tags
        logger.info("\nTesting tag creation...")
        jazz_tag = manager.create_or_get_tag("Jazz", "Genre")
        logger.info(f"✅ Jazz tag: {jazz_tag.Name} (ID: {jazz_tag.ID})")

        party_tag = manager.create_or_get_tag("Party", "Party")
        logger.info(f"✅ Party tag: {party_tag.Name} (ID: {party_tag.ID})")

        # Test with a real track (if available)
        logger.info("\nTesting tag linking (with first available content)...")
        content = db.get_content().first()
        if content:
            logger.info(f"Found content: {content.Title} by {content.ArtistName}")

            # Link to tag
            success = manager.link_content_to_tag(content, jazz_tag)
            logger.info(f"✅ Link created: {success}")

            # Get tags for content
            tags = manager.get_content_tag_names(content, group_name="Genre")
            logger.info(f"✅ Genre tags for content: {tags}")

            # Unlink from tag
            success = manager.unlink_content_from_tag(content, jazz_tag)
            logger.info(f"✅ Link removed: {success}")

            # Rollback to not affect database
            db.rollback()
        else:
            logger.info("⚠️  No content found in database, skipping link tests")

        db.close()
        logger.info("\n✅ MyTag manager test completed")

    except Exception as e:
        logger.error(f"❌ MyTag manager test failed: {e}")
        import traceback

        traceback.print_exc()


def test_playlist_sync(playlist_name: str = None):
    """Test the full playlist synchronization.

    Args:
        playlist_name: Name of playlist to sync (None to list available)
    """
    logger.info("\n" + "=" * 60)
    logger.info("Testing Playlist Synchronization")
    logger.info("=" * 60)

    try:
        # Get config
        config = get_config()
        logger.info(f"MP3 Directory: {config.mp3_directory}")
        logger.info(f"Playlists Root: {config.mp3_directory / 'Playlists'}")

        # List available playlists
        playlists_root = config.mp3_directory / "Playlists"
        if not playlists_root.exists():
            logger.error(f"❌ Playlists directory does not exist: {playlists_root}")
            return

        available_playlists = [p.name for p in playlists_root.iterdir() if p.is_dir()]
        logger.info(f"\nAvailable playlists ({len(available_playlists)}):")
        for i, name in enumerate(available_playlists, 1):
            logger.info(f"  {i}. {name}")

        if playlist_name is None:
            logger.info("\n⚠️  No playlist specified, skipping sync test")
            logger.info("   To test sync, call: test_playlist_sync('playlist_name')")
            return

        if playlist_name not in available_playlists:
            logger.error(f"❌ Playlist '{playlist_name}' not found")
            return

        # Create service
        service = RekordboxService(config)

        # Perform sync
        logger.info(f"\n🔄 Syncing playlist: {playlist_name}")
        result = service.sync_playlist_with_mytags(playlist_name)

        # Display results
        logger.info("\n📊 Sync Results:")
        logger.info(f"  Playlist: {result['playlist_name']}")
        logger.info(f"  MP3 tracks: {result['mp3_tracks_count']}")
        logger.info(f"  Rekordbox tracks (before): {result['rekordbox_tracks_before']}")
        logger.info(f"  Tracks added: {result['tracks_added']}")
        logger.info(f"  Tracks removed: {result['tracks_removed']}")
        logger.info(f"  Playlist deleted: {result['playlist_deleted']}")
        logger.info(f"  Final track count: {result['final_track_count']}")

        logger.info("\n✅ Playlist sync test completed successfully")

    except Exception as e:
        logger.error(f"❌ Playlist sync test failed: {e}")
        import traceback

        traceback.print_exc()


def interactive_menu():
    """Interactive menu for testing."""
    print("\n" + "=" * 60)
    print("Rekordbox Playlist Sync - Test Menu")
    print("=" * 60)
    print("\n1. Test Playlist Name Parser")
    print("2. Test MyTag Manager")
    print("3. Test Playlist Synchronization (list playlists)")
    print("4. Test Playlist Synchronization (sync specific playlist)")
    print("5. Run All Tests")
    print("0. Exit")

    choice = input("\nEnter your choice: ").strip()

    if choice == "1":
        test_playlist_name_parser()
    elif choice == "2":
        test_mytag_manager()
    elif choice == "3":
        test_playlist_sync()
    elif choice == "4":
        playlist_name = input("Enter playlist name: ").strip()
        test_playlist_sync(playlist_name)
    elif choice == "5":
        test_playlist_name_parser()
        test_mytag_manager()
        test_playlist_sync()
    elif choice == "0":
        print("Goodbye!")
        sys.exit(0)
    else:
        print("Invalid choice!")

    # Ask to continue
    cont = input("\nPress Enter to continue or 'q' to quit: ").strip().lower()
    if cont == "q":
        print("Goodbye!")
        sys.exit(0)


def main():
    """Main entry point."""
    print("🧪 Rekordbox Playlist Synchronization Test Suite")
    print("=" * 60)

    if not PYREKORDBOX_AVAILABLE:
        print("❌ pyrekordbox is not available")
        return

    # Check if specific test requested via command line
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        if test_type == "parser":
            test_playlist_name_parser()
        elif test_type == "mytag":
            test_mytag_manager()
        elif test_type == "sync":
            playlist_name = sys.argv[2] if len(sys.argv) > 2 else None
            test_playlist_sync(playlist_name)
        elif test_type == "all":
            test_playlist_name_parser()
            test_mytag_manager()
            test_playlist_sync()
        else:
            print(f"Unknown test type: {test_type}")
            print("Usage: python test_rekordbox_sync.py [parser|mytag|sync|all]")
            print("       python test_rekordbox_sync.py sync <playlist_name>")
    else:
        # Interactive mode
        while True:
            interactive_menu()


if __name__ == "__main__":
    main()
