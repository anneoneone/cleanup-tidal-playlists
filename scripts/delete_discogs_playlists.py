#!/usr/bin/env python3
"""Delete all Tidal playlists that begin with 'Discogs'."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.services.tidal_service import TidalApiService


def delete_discogs_playlists():
    """Find and delete all playlists starting with 'Discogs'."""
    # Initialize Tidal service
    token_file = Path.home() / ".config" / "tidal-cleanup" / "token.json"
    tidal_service = TidalApiService(token_file)

    print("Connecting to Tidal...")
    tidal_service.connect()
    print("✓ Connected to Tidal\n")

    # Get all playlists
    print("Fetching playlists...")
    playlists = tidal_service.get_playlists()
    print(f"✓ Found {len(playlists)} total playlists\n")

    # Filter playlists that start with "Discogs"
    discogs_playlists = [p for p in playlists if p.name.startswith("Discogs")]

    if not discogs_playlists:
        print("No playlists found that begin with 'Discogs'")
        return

    print(f"Found {len(discogs_playlists)} playlists starting with 'Discogs':")
    print("-" * 80)
    for playlist in discogs_playlists:
        print(f"  - {playlist.name} (ID: {playlist.tidal_id})")
    print("-" * 80)

    # Ask for confirmation
    prompt = (
        f"\nAre you sure you want to delete these "
        f"{len(discogs_playlists)} playlists? (yes/no): "
    )
    response = input(prompt)

    if response.lower() not in ["yes", "y"]:
        print("Operation cancelled.")
        return

    # Delete playlists
    print("\nDeleting playlists...")
    deleted_count = 0
    failed_count = 0

    for playlist in discogs_playlists:
        try:
            # Get the tidalapi playlist object to delete
            tidal_playlist = tidal_service.session.playlist(playlist.tidal_id)

            # Delete the playlist
            tidal_playlist.delete()

            print(f"✓ Deleted: {playlist.name}")
            deleted_count += 1

        except Exception as e:
            print(f"✗ Failed to delete {playlist.name}: {e}")
            failed_count += 1

    # Summary
    print("\n" + "=" * 80)
    print("DELETION SUMMARY")
    print("=" * 80)
    print(f"Successfully deleted: {deleted_count}")
    print(f"Failed to delete: {failed_count}")
    print(f"Total processed: {len(discogs_playlists)}")


if __name__ == "__main__":
    try:
        delete_discogs_playlists()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
