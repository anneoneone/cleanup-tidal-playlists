#!/usr/bin/env python3
"""Check if tracks matching a smart playlist have correct tags."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

print("=" * 80)
print("CHECKING SMART PLAYLIST: House Progressive")
print("=" * 80)

# Get the House Progressive smart playlist
smart_playlist = (
    service.db.query(db6.DjmdPlaylist)
    .filter(
        db6.DjmdPlaylist.Name == "House Progressive", db6.DjmdPlaylist.Attribute == 4
    )
    .first()
)

if not smart_playlist:
    print("Smart playlist not found")
    service.close()
    sys.exit(1)

print(f"\nPlaylist ID: {smart_playlist.ID}")
print(f"SmartList condition: {smart_playlist.SmartList[:100]}...")

# The smart playlist should show tracks that have Genre::House Progressive tag
# Let's check how many tracks in the database have this tag

# Get the House Progressive MyTag
mytag = (
    service.db.query(db6.DjmdMyTag)
    .filter(db6.DjmdMyTag.Name == "House Progressive", db6.DjmdMyTag.Attribute == 0)
    .first()
)

if mytag:
    print(f"\nMyTag 'House Progressive' ID: {mytag.ID}")

    # Get tracks with this tag
    tagged_tracks = (
        service.db.query(db6.DjmdSongMyTag)
        .filter(db6.DjmdSongMyTag.MyTagID == mytag.ID)
        .all()
    )

    print(f"Tracks with Genre::House Progressive tag: {len(tagged_tracks)}")

    if tagged_tracks:
        print(f"\nFirst 5 tracks with this tag:")
        for i, link in enumerate(tagged_tracks[:5], 1):
            content = (
                service.db.query(db6.DjmdContent)
                .filter(db6.DjmdContent.ID == link.ContentID)
                .first()
            )

            if content:
                print(f"  {i}. {content.Title} - {content.ArtistName}")
    else:
        print("\n⚠️  NO TRACKS have the Genre::House Progressive tag!")
        print("This means:")
        print("  1. Either no playlists with 🏃🏼‍♂️ emoji have been synced yet")
        print("  2. Or the emoji normalization fix needs to be applied by re-syncing")
else:
    print("\nMyTag 'House Progressive' not found!")

print("\n" + "=" * 80)

service.close()
