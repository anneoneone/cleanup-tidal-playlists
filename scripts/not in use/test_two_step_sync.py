#!/usr/bin/env python3
"""Test script for the new two-step sync algorithm.

This script demonstrates the usage of the refactored sync algorithm:
1. Creates intelligent playlist structure based on rekordbox_mytag_mapping.json
2. Syncs track tags from MP3 directories
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_two_step_sync() -> None:
    """Test the two-step sync algorithm."""
    logger.info("🧪 Testing Two-Step Sync Algorithm")
    logger.info("=" * 60)

    # Get configuration
    config = get_config()

    # Create service
    service = RekordboxService(config)

    try:
        # Execute two-step sync
        results = service.sync_all_with_two_step_algorithm()

        # Display results
        logger.info("\n" + "=" * 60)
        logger.info("RESULTS")
        logger.info("=" * 60)

        logger.info("\nStep 1: Intelligent Playlist Structure")
        logger.info("-" * 40)
        step1 = results["step1"]
        logger.info(f"  Genres Created: {step1.get('genres_created', 0)}")
        logger.info(f"  Genres Updated: {step1.get('genres_updated', 0)}")
        logger.info(
            f"  Event Folders Created: {step1.get('events_folders_created', 0)}"
        )
        logger.info(f"  Total Playlists: {step1.get('total_playlists', 0)}")

        logger.info("\nStep 2: Track Tag Synchronization")
        logger.info("-" * 40)
        step2 = results["step2"]
        logger.info(f"  Playlists Processed: {step2.get('playlists_processed', 0)}")
        logger.info(f"  Tracks Added: {step2.get('tracks_added', 0)}")
        logger.info(f"  Tracks Updated: {step2.get('tracks_updated', 0)}")
        logger.info(f"  Tracks Removed: {step2.get('tracks_removed', 0)}")
        logger.info(f"  Skipped Playlists: {step2.get('skipped_playlists', 0)}")

        logger.info("\n" + "=" * 60)
        logger.info("✅ Test completed successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        service.close()


def main():
    """Main entry point."""
    print("\n🎵 Two-Step Sync Algorithm Test")
    print("=" * 60)
    print("This test will:")
    print("  1. Create/update intelligent playlist structure")
    print("  2. Sync track tags from MP3 directories")
    print("=" * 60)

    response = input("\nProceed with test? (y/N): ").strip().lower()

    if response == "y":
        test_two_step_sync()
    else:
        print("Test cancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
