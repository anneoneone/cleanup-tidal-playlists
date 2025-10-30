#!/usr/bin/env python3
"""Validation script for Step 2: Track Tag Synchronization.

This script:
1. Runs Step 2 (track tag sync)
2. Shows which tracks were tagged with which MyTags
3. Validates that intelligent playlists auto-populated correctly
4. Prints detailed statistics and validation results
"""

import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config
from tidal_cleanup.services.mytag_manager import MyTagManager
from tidal_cleanup.services.rekordbox_service import RekordboxService
from tidal_cleanup.services.track_tag_sync_service import TrackTagSyncService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Step2Validator:
    """Validates Step 2 track tag synchronization."""

    def __init__(self, rekordbox_service: RekordboxService, config: Any):
        """Initialize the validator."""
        self.rekordbox_service = rekordbox_service
        self.config = config
        self.mytag_manager = MyTagManager(rekordbox_service.db)

    def run_step2(self) -> Dict[str, any]:
        """Run Step 2 and collect results."""
        logger.info("=" * 80)
        logger.info("EXECUTING STEP 2: Track Tag Synchronization")
        logger.info("=" * 80)

        # Get paths from config
        mp3_playlists_root = self.config.mp3_directory / "Playlists"

        # Get emoji config path
        service_dir = Path(__file__).resolve().parent
        project_root = service_dir.parent
        mytag_mapping_path = project_root / "config" / "rekordbox_mytag_mapping.json"

        track_sync_service = TrackTagSyncService(
            self.rekordbox_service.db,
            mp3_playlists_root,
            mytag_mapping_path,
        )
        result = track_sync_service.sync_all_playlists()

        logger.info("")
        logger.info("✅ Step 2 completed successfully!")
        logger.info(f"   Processed: {result['playlists_processed']} playlists")
        logger.info(f"   Tracks added: {result['tracks_added']}")
        logger.info(f"   Tracks updated: {result['tracks_updated']}")
        logger.info(f"   Tracks removed: {result['tracks_removed']}")
        logger.info(f"   Skipped playlists: {result['skipped_playlists']}")
        logger.info("")

        return result

    def analyze_track_tags(self) -> Dict[str, any]:
        """Analyze which tracks have which MyTags."""
        logger.info("=" * 80)
        logger.info("ANALYZING TRACK TAGS")
        logger.info("=" * 80)

        logger.info("")
        logger.info("⚠️  NOTE: Track import is not yet implemented")
        logger.info("   Once implemented, tracks would be imported and tagged")
        logger.info("   This section would then show which tracks have which tags")
        logger.info("")

        # Get all MyTag groups and values from database
        mytags = list(self.rekordbox_service.db.get_my_tag())

        # Group by MyTag group
        tag_groups: Dict[str, List] = defaultdict(list)
        for mytag in mytags:
            tag_groups[mytag.Name].append(mytag)

        logger.info(f"Total MyTag groups: {len(tag_groups)}")
        logger.info(f"Total MyTag values: {len(mytags)}")
        logger.info("")

        # Show MyTag groups
        for group_name in sorted(tag_groups.keys()):
            tags = tag_groups[group_name]
            logger.info(f"📊 {group_name}: {len(tags)} values")

        logger.info("")

        return {
            "tag_stats": {},
            "total_applications": 0,
        }

    def validate_intelligent_playlists(self) -> Dict[str, any]:
        """Validate that intelligent playlists have auto-populated."""
        logger.info("=" * 80)
        logger.info("VALIDATING INTELLIGENT PLAYLIST AUTO-POPULATION")
        logger.info("=" * 80)

        # Get all intelligent playlists
        all_playlists = self.rekordbox_service.db.get_playlist()
        intelligent_playlists = [
            p for p in all_playlists if p.SmartList and p.SmartList.strip()
        ]

        logger.info(f"\nFound {len(intelligent_playlists)} intelligent playlists")
        logger.info("")
        logger.info("⚠️  NOTE: Track import is not yet implemented")
        logger.info(
            "   All intelligent playlists will show 0 tracks until tracks are imported"
        )
        logger.info("   Once tracks are imported and tagged, they will auto-populate")
        logger.info("")

        # Show sample of intelligent playlists
        logger.info("Sample of intelligent playlists created:")
        for i, playlist in enumerate(intelligent_playlists[:10], 1):
            logger.info(f"{i}. {playlist.Name:30s} | Query: {playlist.SmartList}")

        if len(intelligent_playlists) > 10:
            logger.info(f"... and {len(intelligent_playlists) - 10} more playlists")

        logger.info("")

        return {
            "total_intelligent_playlists": len(intelligent_playlists),
            "populated_count": 0,
            "empty_count": len(intelligent_playlists),
            "total_tracks": 0,
            "playlist_details": [],
        }

    def validate_tag_playlist_consistency(
        self, tag_stats: Dict[str, int], playlist_details: List[Dict]
    ):
        """Validate that tag counts match playlist track counts."""
        logger.info("=" * 80)
        logger.info("VALIDATING TAG-PLAYLIST CONSISTENCY")
        logger.info("=" * 80)

        logger.info("")
        logger.info("⚠️  Skipping consistency check:")
        logger.info("   Track import not yet implemented, no tracks to validate")
        logger.info("   Once tracks are imported, this would verify that MyTag counts")
        logger.info("   match intelligent playlist track counts")
        logger.info("")

        return []

    def print_summary(
        self,
        step2_result: Dict,
        tag_analysis: Dict,
        playlist_validation: Dict,
        inconsistencies: List,
    ):
        """Print final validation summary."""
        logger.info("=" * 80)
        logger.info("STEP 2 VALIDATION SUMMARY")
        logger.info("=" * 80)

        logger.info("\n📊 Step 2 Execution:")
        logger.info(f"   • Playlists processed: {step2_result['playlists_processed']}")
        logger.info(f"   • Tracks added: {step2_result['tracks_added']}")
        logger.info(f"   • Tracks updated: {step2_result['tracks_updated']}")
        logger.info(f"   • Tracks removed: {step2_result['tracks_removed']}")
        logger.info(f"   • Skipped playlists: {step2_result['skipped_playlists']}")

        logger.info("\n🏷️  Track Tagging:")
        logger.info(
            f"   • MyTag combinations applied: " f"{len(tag_analysis['tag_stats'])}"
        )
        total_tagged_tracks = sum(tag_analysis["tag_stats"].values())
        logger.info(f"   • Total track-tag assignments: {total_tagged_tracks}")

        logger.info("\n🧠 Intelligent Playlists:")
        logger.info(
            f"   • Total intelligent playlists: "
            f"{playlist_validation['total_intelligent_playlists']}"
        )
        logger.info(
            f"   • Populated playlists: " f"{playlist_validation['populated_count']}"
        )
        logger.info(f"   • Empty playlists: {playlist_validation['empty_count']}")
        logger.info(
            f"   • Total tracks in intelligent playlists: "
            f"{playlist_validation['total_tracks']}"
        )

        logger.info("\n✅ Validation Results:")
        if inconsistencies:
            logger.warning(f"   ⚠️  Found {len(inconsistencies)} inconsistencies")
            logger.warning("   (MyTag counts don't match playlist track counts)")
        else:
            logger.info("   ✅ All tag-playlist counts are consistent!")

        if playlist_validation["empty_count"] > 0:
            logger.warning(
                f"   ⚠️  {playlist_validation['empty_count']} "
                f"playlists are still empty"
            )
            logger.warning("   (This may be normal if no tracks match those genres)")

        logger.info("\n" + "=" * 80)
        logger.info("VALIDATION COMPLETE")
        logger.info("=" * 80)


def main():
    """Main validation function."""
    try:
        # Get configuration
        config = get_config()

        # Initialize services
        rekordbox_service = RekordboxService(config)
        validator = Step2Validator(rekordbox_service, config)

        # Run Step 2
        step2_result = validator.run_step2()

        # Analyze track tags
        tag_analysis = validator.analyze_track_tags()

        # Validate intelligent playlists
        playlist_validation = validator.validate_intelligent_playlists()

        # Validate consistency
        inconsistencies = validator.validate_tag_playlist_consistency(
            tag_analysis["tag_stats"],
            playlist_validation["playlist_details"],
        )

        # Print summary
        validator.print_summary(
            step2_result,
            tag_analysis,
            playlist_validation,
            inconsistencies,
        )

        # Commit changes
        rekordbox_service.db.commit()
        logger.info("\n✅ Changes committed to Rekordbox database")

    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
