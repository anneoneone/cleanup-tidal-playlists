#!/usr/bin/env python3
"""Check Status MyTags."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

# Get Status group
status_group = (
    service.db.query(db6.DjmdMyTag)
    .filter(db6.DjmdMyTag.Name == "Status", db6.DjmdMyTag.Attribute == 1)
    .first()
)

if status_group:
    print(f"Status Group ID: {status_group.ID}\n")

    # Get all Status values
    values = (
        service.db.query(db6.DjmdMyTag)
        .filter(db6.DjmdMyTag.Attribute == 0, db6.DjmdMyTag.ParentID == status_group.ID)
        .all()
    )

    print("Status MyTag values:")
    for v in values:
        print(f"  - {v.Name} (ID: {v.ID})")
else:
    print("Status group not found")

service.close()
