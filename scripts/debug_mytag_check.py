#!/usr/bin/env python3
"""Debug script to check MyTag assignments."""

from pyrekordbox.db6 import DjmdSongMyTag

from tidal_cleanup.config import Config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = Config()
service = RekordboxService(config)

if service.db:
    # Test MyTag IDs from the first playlist
    test_mytag_ids = [91468782, 39241783]

    for mytag_id in test_mytag_ids:
        print(f"\nChecking MyTag ID: {mytag_id}")

        # Query tracks with this MyTag
        tracks_with_tag = (
            service.db.query(DjmdSongMyTag)
            .filter(DjmdSongMyTag.MyTagID == str(mytag_id))
            .all()
        )

        print(f"  Found {len(tracks_with_tag)} track assignments")

        if len(tracks_with_tag) > 0:
            print(f"  First few tracks:")
            for track_tag in tracks_with_tag[:3]:
                print(f"    - TrackID: {track_tag.ID}, MyTagID: {track_tag.MyTagID}")

    # Check total MyTag assignments
    total_assignments = service.db.query(DjmdSongMyTag).count()
    print(f"\n\nTotal MyTag assignments in database: {total_assignments}")

    # Check a few sample MyTag IDs
    sample_mytags = service.db.query(DjmdSongMyTag).limit(5).all()
    print(f"\nSample MyTag assignments:")
    for tag in sample_mytags:
        print(f"  TrackID: {tag.ID}, MyTagID: {tag.MyTagID}")
else:
    print("❌ Database not available")
