#!/usr/bin/env python3
"""Script to remove all empty playlists from Rekordbox database."""

import logging

from pyrekordbox import Rekordbox6Database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def find_empty_playlists(db):
    """Find all empty playlists in database (excluding folders)."""
    all_playlists = db.get_playlist().all()
    logger.info(f"📊 Found {len(all_playlists)} total playlist entries")

    empty_playlists = []
    for playlist in all_playlists:
        # Skip folders (Attribute == 1)
        if playlist.Attribute == 1:
            continue

        # Only consider actual playlists that have no songs
        if not playlist.Songs or len(playlist.Songs) == 0:
            empty_playlists.append(playlist)
            logger.info(
                f"📭 Empty playlist found: '{playlist.Name}' "
                f"(ID: {playlist.ID}, Attribute: {playlist.Attribute})"
            )

    return empty_playlists


def delete_playlists(db, playlists):
    """Delete specified playlists from database."""
    deleted_count = 0
    for playlist in playlists:
        try:
            logger.info(f"  Deleting: {playlist.Name}")
            db.delete_playlist(playlist)
            deleted_count += 1
        except Exception as e:
            logger.error(f"  ❌ Failed to delete '{playlist.Name}': {e}")

    db.commit()
    return deleted_count


def remove_empty_playlists() -> None:
    """Remove all empty playlists from Rekordbox database."""
    try:
        # Connect to database
        logger.info("🔌 Connecting to Rekordbox database...")
        db = Rekordbox6Database()
        logger.info("✅ Connected to Rekordbox database")

        # Get all playlists and find empty ones
        logger.info("📋 Fetching all playlists...")
        empty_playlists = find_empty_playlists(db)

        if not empty_playlists:
            logger.info("✅ No empty playlists found!")
            db.close()
            return

        logger.info(f"\n🗑️ Found {len(empty_playlists)} empty playlists to delete:")
        for playlist in empty_playlists:
            logger.info(f"  - {playlist.Name}")

        # Ask for confirmation
        response = (
            input(f"\n⚠️  Delete {len(empty_playlists)} empty playlists? (y/N): ")
            .lower()
            .strip()
        )

        if response != "y":
            logger.info("❌ Deletion cancelled")
            db.close()
            return

        # Delete empty playlists
        logger.info("\n🗑️ Deleting empty playlists...")
        deleted_count = delete_playlists(db, empty_playlists)
        logger.info(f"✅ Successfully deleted {deleted_count} empty playlists")

        # Close database
        db.close()
        logger.info("🔌 Database connection closed")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    logger.info("🧹 Starting empty playlist cleanup...\n")
    remove_empty_playlists()
    logger.info("\n🎉 Cleanup completed!")
