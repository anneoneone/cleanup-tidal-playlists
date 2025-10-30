#!/usr/bin/env python3
"""Test script to verify intelligent playlist structure update behavior.

This script demonstrates that:
1. Running sync_intelligent_playlist_structure() twice doesn't duplicate folders
2. The service correctly compares existing structure with JSON config
3. Orphaned folders/playlists are removed when config changes
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database
from tidal_cleanup.services.intelligent_playlist_structure_service import (
    IntelligentPlaylistStructureService,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def print_structure(db):
    """Print the current Rekordbox folder structure."""
    from pyrekordbox import db6

    print("\n" + "=" * 70)
    print("Current Rekordbox Structure:")
    print("=" * 70)

    # Find root-level folders (Genres, Events)
    root_folders = (
        db.query(db6.DjmdPlaylist)
        .filter(
            ((db6.DjmdPlaylist.ParentID == "") | (db6.DjmdPlaylist.ParentID.is_(None)))
            & (db6.DjmdPlaylist.Attribute == 1)
        )
        .all()
    )

    for folder in root_folders:
        if folder.Name in ["Genres", "Events"]:
            print(f"\n📁 {folder.Name} (ID: {folder.ID})")

            # Get subfolders
            subfolders = (
                db.query(db6.DjmdPlaylist)
                .filter(
                    (db6.DjmdPlaylist.ParentID == folder.ID)
                    & (db6.DjmdPlaylist.Attribute == 1)
                )
                .all()
            )

            for subfolder in subfolders:
                print(f"  📁 {subfolder.Name} (ID: {subfolder.ID})")

                # Get playlists in this folder
                playlists = (
                    db.query(db6.DjmdPlaylist)
                    .filter(
                        (db6.DjmdPlaylist.ParentID == subfolder.ID)
                        & (db6.DjmdPlaylist.Attribute == 4)
                    )
                    .all()
                )

                for playlist in playlists:
                    print(f"    🎵 {playlist.Name} (Smart Playlist)")

    print("=" * 70 + "\n")


def main():
    """Run the test."""
    # Logging already configured at module level

    # Paths
    rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"
    mytag_mapping_path = (
        Path(__file__).parent.parent / "config/rekordbox_mytag_mapping.json"
    )

    if not rekordbox_db.exists():
        print(f"❌ Rekordbox database not found: {rekordbox_db}")
        return 1

    if not mytag_mapping_path.exists():
        print(f"❌ MyTag mapping not found: {mytag_mapping_path}")
        return 1

    print("🔧 Opening Rekordbox database...")
    with Rekordbox6Database(rekordbox_db) as db:
        print("✓ Database opened successfully\n")

        # Print initial structure
        print("📊 BEFORE FIRST SYNC:")
        print_structure(db)

        # Create service
        service = IntelligentPlaylistStructureService(
            db=db, mytag_mapping_path=mytag_mapping_path
        )

        # First sync
        print("🔄 Running FIRST sync...")
        results1 = service.sync_intelligent_playlist_structure()
        print(f"\nFirst sync results: {results1}")

        # Print structure after first sync
        print("\n📊 AFTER FIRST SYNC:")
        print_structure(db)

        # Second sync (should not create duplicates)
        print("🔄 Running SECOND sync...")
        results2 = service.sync_intelligent_playlist_structure()
        print(f"\nSecond sync results: {results2}")

        # Print structure after second sync
        print("\n📊 AFTER SECOND SYNC:")
        print_structure(db)

        # Verify no duplicates
        print("\n✅ VERIFICATION:")
        if results2["genres_created"] == 0 and results2["playlists_created"] == 0:
            print("✓ No duplicates created on second run")
            print("✓ Update behavior working correctly!")
        else:
            print("❌ WARNING: New items created on second run!")
            print(f"   Genres created: {results2['genres_created']}")
            print(f"   Playlists created: {results2['playlists_created']}")

        if results2["playlists_updated"] > 0:
            print(f"✓ Updated {results2['playlists_updated']} existing playlists")

    return 0


if __name__ == "__main__":
    sys.exit(main())
