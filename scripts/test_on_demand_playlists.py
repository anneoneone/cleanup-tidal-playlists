#!/usr/bin/env python3
"""Test on-demand intelligent playlist creation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database

from tidal_cleanup.services.intelligent_playlist_structure_service import (
    IntelligentPlaylistStructureService,
)


def test_on_demand_creation():
    """Test on-demand intelligent playlist creation."""

    rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"
    mytag_mapping_path = (
        Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
    )

    if not rekordbox_db.exists():
        print(f"❌ Rekordbox database not found: {rekordbox_db}")
        return 1

    print("🔧 Opening Rekordbox database...")

    with Rekordbox6Database(rekordbox_db) as db:
        service = IntelligentPlaylistStructureService(
            db=db, mytag_mapping_path=mytag_mapping_path
        )

        print("\n✅ Service initialized\n")

        # Test cases
        test_cases = [
            ("House House", None, None),  # No energy, no status
            ("House House", "Up", None),  # With energy, no status
            ("House House", None, "Archived"),  # No energy, with status
            ("House House", "Up", "Archived"),  # With energy and status
            ("House Italo", "High", "Old"),  # Different genre, energy, status
        ]

        print("Creating intelligent playlists on-demand:\n")

        for genre, energy, status in test_cases:
            try:
                playlist = service.get_or_create_intelligent_playlist(
                    genre_value=genre,
                    energy_value=energy,
                    status_value=status,
                )

                status_str = status if status else "Current"
                energy_str = f", Energy={energy}" if energy else ""

                print(f"✅ {playlist.Name} (ID: {playlist.ID})")
                print(f"   → Genre={genre}{energy_str}, Status={status_str}")
                print()

            except Exception as e:
                print(f"❌ Failed to create playlist: {e}\n")

        # Commit changes
        print("💾 Committing changes...")
        db.commit()

        print("\n✅ Test completed!")

    return 0


if __name__ == "__main__":
    sys.exit(test_on_demand_creation())
