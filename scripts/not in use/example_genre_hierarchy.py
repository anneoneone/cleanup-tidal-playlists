#!/usr/bin/env python3
"""Example script demonstrating genre hierarchy in Rekordbox sync.

This script shows how the hierarchical playlist organization works with the new genre
hierarchy feature.
"""

from pathlib import Path

from tidal_cleanup.config import Config
from tidal_cleanup.services import RekordboxService


def main():
    """Demonstrate genre hierarchy usage."""
    # Load config
    config = Config()

    # Initialize Rekordbox service
    service = RekordboxService(config)

    # Define paths to config files (optional - will use defaults if None)
    emoji_config = Path("config/rekordbox_mytag_mapping.json")
    hierarchy_config = Path("config/rekordbox_genre_hierarchy.json")

    print("=" * 70)
    print("Rekordbox Genre Hierarchy Example")
    print("=" * 70)
    print()

    # Check if hierarchy config exists
    if hierarchy_config.exists():
        print("✓ Genre hierarchy enabled")
        print(f"  Config: {hierarchy_config}")
        print()
    else:
        print("✗ Genre hierarchy disabled (config not found)")
        print(f"  Expected at: {hierarchy_config}")
        print()
        print("Playlists will be organized in flat structure.")
        return

    # Example 1: Sync a single House playlist
    print("Example 1: Syncing House playlist")
    print("-" * 70)
    playlist_name = "☀️ Summer House 2024"
    print(f"Playlist: {playlist_name}")
    print("Expected hierarchy: House/House House/")
    print()

    # Uncomment to actually sync:
    # result = service.sync_playlist_with_mytags(
    #     playlist_name,
    #     emoji_config_path=emoji_config,
    #     genre_hierarchy_config_path=hierarchy_config
    # )
    # print(f"Result: {result}")

    # Example 2: Sync a Techno playlist
    print("Example 2: Syncing Techno playlist")
    print("-" * 70)
    playlist_name = "🏢 Dark Techno Set"
    print(f"Playlist: {playlist_name}")
    print("Expected hierarchy: Techno/Techno Techno/")
    print()

    # Example 3: Sync a Party playlist
    print("Example 3: Syncing Party playlist")
    print("-" * 70)
    playlist_name = "🎉 New Year Party 2024"
    print(f"Playlist: {playlist_name}")
    print("Expected hierarchy: Partys/Party/")
    print()

    # Example 4: Pre-create all folders before batch sync
    print("Example 4: Pre-creating all folders")
    print("-" * 70)
    print("This ensures efficient batch syncing...")

    # Uncomment to actually pre-create folders:
    # service.ensure_genre_party_folders(
    #     emoji_config_path=emoji_config,
    #     genre_hierarchy_config_path=hierarchy_config
    # )

    print()
    print("=" * 70)
    print("Done! Uncomment the sync calls to actually run the sync.")
    print("=" * 70)


if __name__ == "__main__":
    main()
