#!/usr/bin/env python3
"""Delete all playlists from Rekordbox database.

WARNING: This will delete ALL playlists (including intelligent playlists and folders).
Use with caution!
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database, db6


def confirm_deletion() -> bool:
    """Ask user to confirm deletion."""
    print("⚠️  WARNING: This will delete ALL playlists from Rekordbox!")
    response = input("Are you sure? (type 'yes' to confirm): ")
    if response.lower() != "yes":
        return False

    response = input("Delete ALL playlists? (type 'DELETE' to confirm): ")
    return response == "DELETE"


def delete_playlists_by_type(db, playlists, playlist_type):
    """Delete a list of playlists."""
    deleted = 0
    total = len(playlists)

    for playlist in playlists:
        try:
            db.delete(playlist)
            deleted += 1
            if deleted % 10 == 0:
                print(f"  Deleted {deleted}/{total} {playlist_type}...")
        except Exception as e:
            print(f"  ⚠️  Failed to delete {playlist.Name}: {e}")

    return deleted


def delete_all_playlists():
    """Delete all playlists from Rekordbox database."""

    rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"

    if not rekordbox_db.exists():
        print(f"❌ Rekordbox database not found: {rekordbox_db}")
        return 1

    if not confirm_deletion():
        print("❌ Cancelled.")
        return 0

    print("\n🔧 Opening Rekordbox database...")

    with Rekordbox6Database(rekordbox_db) as db:
        all_playlists = db.query(db6.DjmdPlaylist).all()

        print(f"Found {len(all_playlists)} playlists\n")

        if len(all_playlists) == 0:
            print("✅ No playlists to delete")
            return 0

        # Categorize playlists
        folders = [p for p in all_playlists if p.Attribute == 1]
        regular = [p for p in all_playlists if p.Attribute == 0]
        smart = [p for p in all_playlists if p.Attribute == 4]

        print(f"  Folders: {len(folders)}")
        print(f"  Regular: {len(regular)}")
        print(f"  Smart: {len(smart)}\n")

        print("🗑️  Deleting playlists...")

        # Delete in order to avoid foreign key issues
        total_deleted = 0
        total_deleted += delete_playlists_by_type(db, smart, "smart playlists")
        total_deleted += delete_playlists_by_type(db, regular, "regular playlists")

        # Delete folders (children before parents)
        folders_sorted = sorted(
            folders, key=lambda f: (f.ParentID or "", f.Name), reverse=True
        )
        total_deleted += delete_playlists_by_type(db, folders_sorted, "folders")

        print("\n💾 Committing changes...")
        db.commit()

        print(f"\n✅ Successfully deleted {total_deleted} playlists!")

    return 0


if __name__ == "__main__":
    sys.exit(delete_all_playlists())
