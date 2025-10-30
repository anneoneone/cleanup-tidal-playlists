#!/usr/bin/env python3
"""Delete Genres folder to recreate with fix."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

try:
    from pyrekordbox import db6
except ImportError:
    print("pyrekordbox not available")
    sys.exit(1)

config = get_config()
service = RekordboxService(config)

# Find and delete the Genres folder and all its children
genres_folder = (
    service.db.query(db6.DjmdPlaylist)
    .filter(db6.DjmdPlaylist.Name == "Genres", db6.DjmdPlaylist.Attribute == 1)
    .first()
)

events_folder = (
    service.db.query(db6.DjmdPlaylist)
    .filter(db6.DjmdPlaylist.Name == "Events", db6.DjmdPlaylist.Attribute == 1)
    .first()
)

if genres_folder:
    # Delete all children first
    children = (
        service.db.query(db6.DjmdPlaylist)
        .filter(db6.DjmdPlaylist.ParentID == genres_folder.ID)
        .all()
    )

    for child in children:
        # Delete grandchildren
        grandchildren = (
            service.db.query(db6.DjmdPlaylist)
            .filter(db6.DjmdPlaylist.ParentID == child.ID)
            .all()
        )
        for gc in grandchildren:
            service.db.delete(gc)
        service.db.delete(child)

    service.db.delete(genres_folder)
    service.db.commit()
    print(f"✓ Deleted Genres folder and {len(children)} children")
else:
    print("Genres folder not found")

if events_folder:
    # Delete all children first
    children = (
        service.db.query(db6.DjmdPlaylist)
        .filter(db6.DjmdPlaylist.ParentID == events_folder.ID)
        .all()
    )

    for child in children:
        # Delete grandchildren
        grandchildren = (
            service.db.query(db6.DjmdPlaylist)
            .filter(db6.DjmdPlaylist.ParentID == child.ID)
            .all()
        )
        for gc in grandchildren:
            service.db.delete(gc)
        service.db.delete(child)

    service.db.delete(events_folder)
    service.db.commit()
    print(f"✓ Deleted Events folder and {len(children)} children")
else:
    print("Events folder not found")

service.close()
