#!/usr/bin/env python3
"""Example script demonstrating the usage of the refactored Rekordbox service.

This script shows how to use the new playlist synchronization functionality with MyTag
management.
"""

import logging
import sys
from pathlib import Path

# Add project root to path if running as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config  # noqa: E402
from tidal_cleanup.services.rekordbox_service import RekordboxService  # noqa: E402

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def sync_single_playlist(playlist_name: str) -> None:
    """Sync a single playlist.

    Args:
        playlist_name: Name of the playlist to sync
    """
    logger.info(f"Syncing playlist: {playlist_name}")

    # Get configuration
    config = get_config()

    # Create service
    service = RekordboxService(config)

    try:
        # Perform synchronization
        result = service.sync_playlist_with_mytags(playlist_name)

        # Display results
        logger.info("=" * 60)
        logger.info("Sync Results:")
        logger.info("=" * 60)
        logger.info(f"Playlist: {result['playlist_name']}")
        logger.info(f"MP3 tracks: {result['mp3_tracks_count']}")
        logger.info(f"Rekordbox tracks (before): {result['rekordbox_tracks_before']}")
        logger.info(f"Tracks added: {result['tracks_added']}")
        logger.info(f"Tracks removed: {result['tracks_removed']}")

        if result["playlist_deleted"]:
            logger.info("⚠️  Playlist was deleted (no tracks remaining)")
        else:
            logger.info(f"Final track count: {result['final_track_count']}")

        logger.info("✅ Sync completed successfully")

    except Exception as e:
        logger.error(f"❌ Sync failed: {e}")
        raise
    finally:
        # Close database connection
        service.close()


def sync_multiple_playlists(playlist_names: list[str]) -> None:
    """Sync multiple playlists.

    Args:
        playlist_names: List of playlist names to sync
    """
    logger.info(f"Syncing {len(playlist_names)} playlists...")

    # Get configuration
    config = get_config()

    # Create service (reuse connection)
    service = RekordboxService(config)

    results = []
    failed = []

    try:
        for i, playlist_name in enumerate(playlist_names, 1):
            logger.info(f"\n[{i}/{len(playlist_names)}] Syncing: {playlist_name}")

            try:
                result = service.sync_playlist_with_mytags(playlist_name)
                results.append(result)
                logger.info(
                    f"✅ Added: {result['tracks_added']}, "
                    f"Removed: {result['tracks_removed']}"
                )
            except Exception as e:
                logger.error(f"❌ Failed to sync '{playlist_name}': {e}")
                failed.append(playlist_name)

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Batch Sync Summary:")
        logger.info("=" * 60)
        logger.info(f"Total playlists: {len(playlist_names)}")
        logger.info(f"Successfully synced: {len(results)}")
        logger.info(f"Failed: {len(failed)}")

        if failed:
            logger.info("\nFailed playlists:")
            for name in failed:
                logger.info(f"  - {name}")

        # Aggregate statistics
        total_added = sum(r["tracks_added"] for r in results)
        total_removed = sum(r["tracks_removed"] for r in results)
        total_deleted = sum(1 for r in results if r["playlist_deleted"])

        logger.info(f"\nTotal tracks added: {total_added}")
        logger.info(f"Total tracks removed: {total_removed}")
        logger.info(f"Playlists deleted: {total_deleted}")

    finally:
        # Close database connection
        service.close()


def list_available_playlists() -> list[str]:
    """List all available MP3 playlists.

    Returns:
        List of playlist names
    """
    config = get_config()
    playlists_root = config.mp3_directory / "Playlists"

    if not playlists_root.exists():
        logger.error(f"Playlists directory does not exist: {playlists_root}")
        return []

    playlists = [p.name for p in playlists_root.iterdir() if p.is_dir()]
    playlists.sort()

    logger.info(f"Found {len(playlists)} playlists:")
    for i, name in enumerate(playlists, 1):
        logger.info(f"  {i}. {name}")

    return playlists


def main():
    """Main entry point."""
    print("🎵 Rekordbox Playlist Synchronization Example")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python example_rekordbox_sync.py <playlist_name>")
        print("  python example_rekordbox_sync.py --list")
        print("  python example_rekordbox_sync.py --batch <name1> <name2> ...")
        print("\nExamples:")
        print("  python example_rekordbox_sync.py 'Jazzz D 🎷💾'")
        print("  python example_rekordbox_sync.py --list")
        print("  python example_rekordbox_sync.py --batch 'Playlist 1' 'Playlist 2'")
        sys.exit(1)

    if sys.argv[1] == "--list":
        list_available_playlists()
    elif sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("❌ Error: --batch requires at least one playlist name")
            sys.exit(1)
        playlist_names = sys.argv[2:]
        sync_multiple_playlists(playlist_names)
    else:
        playlist_name = sys.argv[1]
        sync_single_playlist(playlist_name)


if __name__ == "__main__":
    main()
