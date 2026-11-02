#!/usr/bin/env python3
"""List all playlists from Rekordbox database."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database, db6


def list_all_playlists():
    """Fetch and display all playlists from Rekordbox database."""
    db = Rekordbox6Database()

    print("\n" + "=" * 80)
    print("ALL PLAYLISTS IN REKORDBOX DATABASE")
    print("=" * 80 + "\n")

    # Get all playlists ordered by hierarchy
    playlists = db.query(db6.DjmdPlaylist).order_by(db6.DjmdPlaylist.Seq).all()

    print(f"Total playlists found: {len(playlists)}\n")

    # Group by parent for better readability
    root_playlists = [p for p in playlists if p.Parent is None or p.Parent == ""]
    child_playlists = [p for p in playlists if p.Parent and p.Parent != ""]

    print("ROOT PLAYLISTS:")
    print("-" * 80)
    for playlist in root_playlists:
        print(f"  ID: {playlist.ID:12} | Name: {playlist.Name}")

    print("\nCHILD PLAYLISTS (grouped by parent):")
    print("-" * 80)

    # Group children by parent
    from collections import defaultdict

    children_by_parent = defaultdict(list)
    for p in child_playlists:
        children_by_parent[p.Parent].append(p)

    sorted_parents = sorted(
        children_by_parent.keys(), key=lambda x: str(x) if x else ""
    )
    for parent_id in sorted_parents:
        children = children_by_parent[parent_id]
        # Find parent name
        parent = next((p for p in playlists if p.ID == parent_id), None)
        parent_name = parent.Name if parent else "Unknown"

        print(f"\n  Parent: {parent_name} (ID: {parent_id})")
        for child in children:
            is_folder = "📁" if child.Attribute == 1 else "📝"
            print(f"    {is_folder} ID: {child.ID:12} | Name: {child.Name}")

    # Count by type
    folders = [p for p in playlists if p.Attribute == 1]
    regular = [p for p in playlists if p.Attribute == 0]
    smart = [p for p in playlists if p.Attribute == 4]

    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"  Total:             {len(playlists)}")
    print(f"  Folders:           {len(folders)}")
    print(f"  Regular playlists: {len(regular)}")
    print(f"  Smart playlists:   {len(smart)}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    list_all_playlists()
