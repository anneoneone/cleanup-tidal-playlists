#!/usr/bin/env python3
"""Validate Step 1: Intelligent Playlist Structure Creation.

This script:
1. Runs Step 1 of the two-step sync algorithm
2. Prints the complete folder/playlist structure in Rekordbox
3. Shows details about intelligent playlists and their queries
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Add project root to path if running as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config  # noqa: E402
from tidal_cleanup.services.intelligent_playlist_structure_service import (  # noqa: E402, E501
    IntelligentPlaylistStructureService,
)
from tidal_cleanup.services.rekordbox_service import RekordboxService  # noqa: E402

try:
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    db6 = None

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class RekordboxStructurePrinter:
    """Prints the Rekordbox folder/playlist structure."""

    def __init__(self, db: Any):
        """Initialize printer.

        Args:
            db: Rekordbox6Database instance
        """
        self.db = db

    def print_structure(self) -> None:
        """Print the complete folder/playlist structure."""
        print("\n" + "=" * 80)
        print("REKORDBOX FOLDER/PLAYLIST STRUCTURE")
        print("=" * 80)

        # Get root-level playlists/folders (where ParentID is empty or null)
        root_items = (
            self.db.query(db6.DjmdPlaylist)
            .filter(
                (db6.DjmdPlaylist.ParentID == "")
                | (db6.DjmdPlaylist.ParentID.is_(None))
            )
            .order_by(db6.DjmdPlaylist.Name)
            .all()
        )

        print(f"\n📁 Root Level ({len(root_items)} items)")
        print("-" * 80)

        for item in root_items:
            self._print_item(item, indent=0)

        print("\n" + "=" * 80)

    def _print_item(self, item: Any, indent: int = 0) -> None:
        """Print a single item (folder or playlist) and its children.

        Args:
            item: DjmdPlaylist instance
            indent: Current indentation level
        """
        indent_str = "  " * indent

        # Determine item type
        if item.Attribute == 1:
            # Folder
            icon = "📁"
            item_type = "FOLDER"
        elif item.Attribute == 0:
            # Playlist
            icon = "🎵"
            item_type = "PLAYLIST"

            # Check if it's an intelligent playlist
            if hasattr(item, "SmartList") and item.SmartList:
                icon = "🧠"
                item_type = "INTELLIGENT PLAYLIST"
        elif item.Attribute == 4:
            # Smart/Intelligent Playlist
            icon = "🧠"
            item_type = "INTELLIGENT PLAYLIST"
        else:
            icon = "❓"
            item_type = f"UNKNOWN (Attr={item.Attribute})"

        # Print item info
        print(f"{indent_str}{icon} {item.Name}")
        print(f"{indent_str}   └─ Type: {item_type}")
        print(f"{indent_str}   └─ ID: {item.ID}")

        # Print SmartList info if it's an intelligent playlist
        if hasattr(item, "SmartList") and item.SmartList:
            smartlist_preview = (
                item.SmartList[:60] + "..."
                if len(item.SmartList) > 60
                else item.SmartList
            )
            print(f"{indent_str}   └─ Query: {smartlist_preview}")

        # Get track count for playlists
        if item.Attribute == 0:
            track_count = (
                self.db.query(db6.DjmdSongPlaylist)
                .filter(db6.DjmdSongPlaylist.PlaylistID == item.ID)
                .count()
            )
            print(f"{indent_str}   └─ Tracks: {track_count}")

        # Get and print children
        children = (
            self.db.query(db6.DjmdPlaylist)
            .filter(db6.DjmdPlaylist.ParentID == item.ID)
            .order_by(db6.DjmdPlaylist.Name)
            .all()
        )

        if children:
            print(f"{indent_str}   └─ Children: {len(children)}")
            for child in children:
                self._print_item(child, indent + 1)
        else:
            print(f"{indent_str}   └─ Children: 0")

        print()  # Empty line for readability

    def print_statistics(self) -> Dict[str, int]:
        """Print overall statistics about the structure.

        Returns:
            Dictionary with statistics
        """
        print("\n" + "=" * 80)
        print("STATISTICS")
        print("=" * 80)

        # Count folders
        folder_count = (
            self.db.query(db6.DjmdPlaylist)
            .filter(db6.DjmdPlaylist.Attribute == 1)
            .count()
        )

        # Count playlists
        playlist_count = (
            self.db.query(db6.DjmdPlaylist)
            .filter(db6.DjmdPlaylist.Attribute == 0)
            .count()
        )

        # Count intelligent playlists (those with SmartList)
        all_playlists = (
            self.db.query(db6.DjmdPlaylist)
            .filter(db6.DjmdPlaylist.Attribute == 0)
            .all()
        )
        intelligent_count = sum(
            1 for p in all_playlists if hasattr(p, "SmartList") and p.SmartList
        )

        # Count MyTag groups and values
        mytag_groups = (
            self.db.query(db6.DjmdMyTag).filter(db6.DjmdMyTag.Attribute == 1).count()
        )

        mytag_values = (
            self.db.query(db6.DjmdMyTag).filter(db6.DjmdMyTag.Attribute == 0).count()
        )

        stats = {
            "folders": folder_count,
            "playlists": playlist_count,
            "intelligent_playlists": intelligent_count,
            "mytag_groups": mytag_groups,
            "mytag_values": mytag_values,
        }

        print(f"\n📊 Total Folders: {folder_count}")
        print(f"📊 Total Playlists: {playlist_count}")
        print(f"📊 Intelligent Playlists: {intelligent_count}")
        print(f"📊 MyTag Groups: {mytag_groups}")
        print(f"📊 MyTag Values: {mytag_values}")

        print("\n" + "=" * 80)

        return stats

    def print_specific_structure(self, folder_name: str) -> None:
        """Print structure for a specific folder.

        Args:
            folder_name: Name of the folder to print
        """
        folder = (
            self.db.query(db6.DjmdPlaylist)
            .filter(
                db6.DjmdPlaylist.Name == folder_name,
                db6.DjmdPlaylist.Attribute == 1,
            )
            .first()
        )

        if not folder:
            print(f"\n❌ Folder '{folder_name}' not found")
            return

        print("\n" + "=" * 80)
        print(f"STRUCTURE FOR: {folder_name}")
        print("=" * 80)
        self._print_item(folder, indent=0)


def test_step1_structure() -> None:
    """Test Step 1 and display the structure."""
    logger.info("🧪 Testing Step 1: Intelligent Playlist Structure Creation")
    logger.info("=" * 80)

    if not PYREKORDBOX_AVAILABLE:
        logger.error("❌ pyrekordbox is not available")
        sys.exit(1)

    # Get configuration
    config = get_config()

    # Create service
    service = RekordboxService(config)

    if not service.db:
        logger.error("❌ Could not connect to Rekordbox database")
        sys.exit(1)

    try:
        # Get mytag mapping path
        mytag_mapping_path = Path("config/rekordbox_mytag_mapping.json")
        if not mytag_mapping_path.exists():
            mytag_mapping_path = (
                Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
            )

        logger.info(f"Using MyTag mapping: {mytag_mapping_path}")

        # Execute Step 1
        logger.info("\n🚀 Executing Step 1...")
        structure_service = IntelligentPlaylistStructureService(
            db=service.db,
            mytag_mapping_path=mytag_mapping_path,
        )

        results = structure_service.sync_intelligent_playlist_structure()

        logger.info("\n✅ Step 1 completed successfully!")
        logger.info(f"   Genres Created: {results.get('genres_created', 0)}")
        logger.info(f"   Genres Updated: {results.get('genres_updated', 0)}")
        logger.info(
            f"   Event Folders Created: {results.get('events_folders_created', 0)}"
        )
        logger.info(f"   Total Playlists: {results.get('total_playlists', 0)}")

        # Print the structure
        printer = RekordboxStructurePrinter(service.db)

        # Print full structure
        printer.print_structure()

        # Print statistics
        printer.print_statistics()

        # Print specific important folders
        logger.info("\n📂 Detailed View of Key Folders:")
        printer.print_specific_structure("Genres")
        printer.print_specific_structure("Events")

        # Verification
        print("\n" + "=" * 80)
        print("VERIFICATION")
        print("=" * 80)

        expected_folders = ["Genres", "Events"]
        found_folders = []

        for folder_name in expected_folders:
            folder = (
                service.db.query(db6.DjmdPlaylist)
                .filter(
                    db6.DjmdPlaylist.Name == folder_name,
                    db6.DjmdPlaylist.Attribute == 1,
                )
                .first()
            )
            if folder:
                found_folders.append(folder_name)
                print(f"✅ '{folder_name}' folder exists")
            else:
                print(f"❌ '{folder_name}' folder NOT found")

        # Verify event subfolders
        event_subfolders = ["Partys", "Sets", "Radio Moafunk"]
        events_folder = (
            service.db.query(db6.DjmdPlaylist)
            .filter(
                db6.DjmdPlaylist.Name == "Events",
                db6.DjmdPlaylist.Attribute == 1,
            )
            .first()
        )

        if events_folder:
            for subfolder_name in event_subfolders:
                subfolder = (
                    service.db.query(db6.DjmdPlaylist)
                    .filter(
                        db6.DjmdPlaylist.Name == subfolder_name,
                        db6.DjmdPlaylist.ParentID == events_folder.ID,
                        db6.DjmdPlaylist.Attribute == 1,
                    )
                    .first()
                )
                if subfolder:
                    print(f"✅ 'Events/{subfolder_name}' subfolder exists")
                else:
                    print(f"❌ 'Events/{subfolder_name}' subfolder NOT found")

        print("\n" + "=" * 80)
        print("✅ VALIDATION COMPLETE")
        print("=" * 80)

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        service.close()


def main():
    """Main entry point."""
    print("\n🎵 Rekordbox Structure Validator - Step 1")
    print("=" * 80)
    print("This script will:")
    print("  1. Execute Step 1 (Intelligent Playlist Structure Creation)")
    print("  2. Display the complete Rekordbox folder/playlist structure")
    print("  3. Show details about intelligent playlists")
    print("  4. Verify expected folders exist")
    print("=" * 80)

    response = input("\nProceed with test? (y/N): ").strip().lower()

    if response == "y":
        test_step1_structure()
    else:
        print("Test cancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
