"""Quick Rekordbox playlist inspector.

This script connects to the local Rekordbox 6 database via pyrekordbox and
prints the playlist/folder tree. Useful for debugging folder placement and
playlist counts after sync runs.

Usage examples:
    python scripts/inspect_rekordbox_playlists.py
    python scripts/inspect_rekordbox_playlists.py --json
    python scripts/inspect_rekordbox_playlists.py --filter "House"
"""

import argparse
import json
import sys
from typing import Dict, List, Optional

try:
    from pyrekordbox import Rekordbox6Database
except ImportError as exc:  # pragma: no cover - requires local Rekordbox install
    print(
        "pyrekordbox is required to run this script: pip install pyrekordbox",
        file=sys.stderr,
    )
    raise


def build_playlist_index(db: Rekordbox6Database) -> Dict[str, dict]:
    """Load all playlists and folders into an index keyed by ID."""
    index: Dict[str, dict] = {}
    playlists = db.get_playlist().all()

    for pl in playlists:
        pid = str(pl.ID)
        parent = str(pl.ParentID) if pl.ParentID else None
        is_folder = pl.Attribute == 1
        index[pid] = {
            "id": pid,
            "name": pl.Name,
            "parent_id": parent,
            "is_folder": is_folder,
            "song_count": (
                len(pl.Songs) if hasattr(pl, "Songs") and not is_folder else 0
            ),
        }

    return index


def build_tree(index: Dict[str, dict]) -> List[dict]:
    """Convert flat index into a tree structure starting from root (ParentID None)."""
    children: Dict[Optional[str], List[dict]] = {}
    for node in index.values():
        children.setdefault(node["parent_id"], []).append(node)

    def attach(node: dict) -> dict:
        node_children = [attach(child) for child in children.get(node["id"], [])]
        node["children"] = sorted(node_children, key=lambda n: n["name"].lower())
        return node

    # Find root nodes: parent_id is None or "root"
    root_nodes = children.get(None, []) + children.get("root", [])
    return sorted(
        [attach(node) for node in root_nodes], key=lambda n: n["name"].lower()
    )


def print_tree(nodes: List[dict], indent: str = "") -> None:
    """Print the tree to stdout in a readable way."""
    for i, node in enumerate(nodes):
        is_last = i == len(nodes) - 1
        connector = "└─" if is_last else "├─"
        prefix = indent + connector
        suffix = "" if node["is_folder"] else f" ({node['song_count']} tracks)"
        print(f"{prefix}{node['name']}{suffix}")
        next_indent = indent + ("  " if is_last else "│ ")
        print_tree(node.get("children", []), next_indent)


def filter_tree(nodes: List[dict], term: str) -> List[dict]:
    """Filter tree to nodes whose name contains term (case-insensitive)."""
    term_lower = term.lower()

    def matches(node: dict) -> bool:
        return term_lower in node["name"].lower()

    def walk(node: dict) -> Optional[dict]:
        filtered_children = []
        for child in node.get("children", []):
            maybe = walk(child)
            if maybe:
                filtered_children.append(maybe)
        if matches(node) or filtered_children:
            clone = dict(node)
            clone["children"] = filtered_children
            return clone
        return None

    result = []
    for node in nodes:
        maybe = walk(node)
        if maybe:
            result.append(maybe)
    return result


def print_flat_list(index: Dict[str, dict]) -> None:
    """Print items as flat list with parent info (fallback when no root items exist)."""
    items = sorted(index.values(), key=lambda n: n["name"].lower())
    print("\nFlat list (parent relationships):")
    print("-" * 80)
    for item in items:
        is_folder = "📁" if item["is_folder"] else "▶️ "
        parent = item["parent_id"] if item["parent_id"] else "[ROOT]"
        suffix = "" if item["is_folder"] else f" ({item['song_count']} tracks)"
        print(f"{is_folder} {item['name']:<45} | Parent: {parent}{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Rekordbox playlists/folders")
    parser.add_argument(
        "--json", action="store_true", help="Output JSON instead of tree text"
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter playlists/folders by name substring",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress informational banner"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Show debug information about structure"
    )
    args = parser.parse_args()

    db = Rekordbox6Database()
    index = build_playlist_index(db)
    tree = build_tree(index)

    total_items = len(index)

    if not args.quiet:
        print(f"Loaded {total_items} Rekordbox playlists/folders")

    if args.debug:
        # Find root items and show structure stats
        root_items = [n for n in index.values() if n["parent_id"] is None]
        print(f"DEBUG: Root items (parent_id=NULL): {len(root_items)}")
        print(f"DEBUG: Root names: {sorted([n['name'] for n in root_items])}")

        # Find Genres and Events
        genres = [n for n in index.values() if n["name"] == "Genres"]
        events = [n for n in index.values() if n["name"] == "Events"]
        print(f"DEBUG: Genres found: {len(genres)}")
        if genres:
            print(
                f"       Genres ID: {genres[0]['id']}, Parent: {genres[0]['parent_id']}"
            )
        print(f"DEBUG: Events found: {len(events)}")
        if events:
            print(
                f"       Events ID: {events[0]['id']}, Parent: {events[0]['parent_id']}"
            )

        # Show parent distribution
        parent_counts = {}
        for node in index.values():
            parent = node["parent_id"] or "[ROOT]"
            parent_counts[parent] = parent_counts.get(parent, 0) + 1
        print(f"DEBUG: Parent distribution (top 10):")
        for parent, count in sorted(parent_counts.items(), key=lambda x: -x[1])[:10]:
            parent_name = (
                index.get(parent, {}).get("name", "?")
                if parent != "[ROOT]"
                else "[ROOT]"
            )
            print(f"       {parent_name}: {count} items")
        print()

    if args.filter:
        tree = filter_tree(tree, args.filter)

    if not tree:
        if args.filter:
            print("No playlists/folders found (after filtering).")
        else:
            print("No root playlists/folders found. All items have a parent.")
            print("Try --debug to see the actual structure.")
        return

    if args.json:
        print(json.dumps(tree, indent=2))
    else:
        print_tree(tree)


if __name__ == "__main__":
    main()
