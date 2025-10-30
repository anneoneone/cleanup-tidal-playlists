#!/usr/bin/env python3
"""Script to fetch all tracks from Rekordbox that have a certain MyTag."""

import sys
from pathlib import Path
from typing import List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

try:
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    db6 = None


def fetch_tracks_by_mytag(
    group_name: str, tag_name: str, verbose: bool = False
) -> List[Tuple[str, str, str]]:
    """Fetch all tracks that have a specific MyTag.

    Args:
        group_name: MyTag group name (e.g., "Genre", "Status")
        tag_name: MyTag value name (e.g., "House Progressive", "Recherche")
        verbose: If True, print detailed information

    Returns:
        List of tuples containing (track_title, artist, file_path)
    """
    if not PYREKORDBOX_AVAILABLE:
        print("❌ pyrekordbox is not available")
        sys.exit(1)

    config = get_config()
    service = RekordboxService(config)

    if not service.db:
        print("❌ Could not connect to Rekordbox database")
        sys.exit(1)

    try:
        # Find the MyTag group
        tag_group = (
            service.db.query(db6.DjmdMyTag)
            .filter(
                db6.DjmdMyTag.Name == group_name,
                db6.DjmdMyTag.Attribute == 1,  # 1 = group/section
            )
            .first()
        )

        if not tag_group:
            print(f"❌ MyTag group '{group_name}' not found")
            return []

        if verbose:
            print(f"✅ Found MyTag group: {group_name} (ID: {tag_group.ID})")

        # Find the specific tag value within the group
        tag_value = (
            service.db.query(db6.DjmdMyTag)
            .filter(
                db6.DjmdMyTag.Name == tag_name,
                db6.DjmdMyTag.ParentID == tag_group.ID,
                db6.DjmdMyTag.Attribute == 0,  # 0 = value
            )
            .first()
        )

        if not tag_value:
            print(f"❌ MyTag value '{tag_name}' not found in group '{group_name}'")
            return []

        if verbose:
            print(f"✅ Found MyTag value: {tag_name} (ID: {tag_value.ID})")

        # Find all SongMyTag links for this tag
        song_mytag_links = (
            service.db.query(db6.DjmdSongMyTag)
            .filter(db6.DjmdSongMyTag.MyTagID == tag_value.ID)
            .all()
        )

        if verbose:
            print(f"✅ Found {len(song_mytag_links)} track-to-tag links")

        # Fetch the actual tracks
        tracks = []
        for link in song_mytag_links:
            content = (
                service.db.query(db6.DjmdContent)
                .filter(db6.DjmdContent.ID == link.ContentID)
                .first()
            )

            if content:
                # Get artist info
                artist_name = "Unknown Artist"
                if content.ArtistID:
                    artist = (
                        service.db.query(db6.DjmdArtist)
                        .filter(db6.DjmdArtist.ID == content.ArtistID)
                        .first()
                    )
                    if artist:
                        artist_name = artist.Name

                tracks.append(
                    (
                        content.Title or "Unknown Title",
                        artist_name,
                        content.FolderPath or "Unknown Path",
                    )
                )

        return tracks

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return []


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch all tracks from Rekordbox that have a certain MyTag"
    )
    parser.add_argument("group", help="MyTag group name (e.g., 'Genre', 'Status')")
    parser.add_argument(
        "tag", help="MyTag value name (e.g., 'House Progressive', 'Recherche')"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print detailed information"
    )

    args = parser.parse_args()

    print(f"\n🔍 Fetching tracks with MyTag: {args.group}::{args.tag}\n")

    tracks = fetch_tracks_by_mytag(args.group, args.tag, args.verbose)

    if tracks:
        print(f"\n✅ Found {len(tracks)} track(s):\n")
        print("=" * 100)
        for i, (title, artist, path) in enumerate(tracks, 1):
            print(f"{i}. {title}")
            print(f"   Artist: {artist}")
            print(f"   Path: {path}")
            print("-" * 100)
    else:
        print("\n❌ No tracks found with this MyTag")


if __name__ == "__main__":
    main()
