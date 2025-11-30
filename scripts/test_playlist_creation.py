#!/usr/bin/env python3
"""Test basic playlist creation."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database

db = Rekordbox6Database()

print("\n=== Testing Playlist Creation ===\n")

try:
    # Test 1: Create root folder
    print("1. Creating root 'Genres' folder...")
    genres_folder = db.create_playlist_folder(name="Genres", parent=None)
    db.flush()
    print(f"   ✓ Created: {genres_folder.Name} (ID: {genres_folder.ID})")

    # Test 2: Create child folder
    print("\n2. Creating child 'House' folder...")
    house_folder = db.create_playlist_folder(name="House", parent=genres_folder.ID)
    db.flush()
    print(f"   ✓ Created: {house_folder.Name} (ID: {house_folder.ID})")

    # Test 3: Commit
    print("\n3. Committing changes...")
    db.commit()
    print("   ✓ Committed")

    # Test 4: Verify
    print("\n4. Verifying in database...")
    from pyrekordbox import db6

    all_folders = (
        db.query(db6.DjmdPlaylist).filter(db6.DjmdPlaylist.Attribute == 1).all()
    )
    print(f"   ✓ Found {len(all_folders)} folders in database:")
    for folder in all_folders:
        print(f"     - {folder.Name} (ID: {folder.ID}, Parent: {folder.ParentID})")

    print("\n✅ All tests passed!\n")

except Exception as e:
    print(f"\n❌ Error: {e}\n")
    import traceback

    traceback.print_exc()
    db.rollback()
