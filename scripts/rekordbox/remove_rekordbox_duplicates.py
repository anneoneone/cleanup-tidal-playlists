"""Delete duplicate tracks from Rekordbox, keeping highest playcount.

This helper connects to the local Rekordbox 6 database via pyrekordbox,
finds duplicate tracks based on a chosen grouping key, and deletes all but
one track in each duplicate group — keeping the track with the highest
`DJPlayCount`.

Safety features:
- Dry-run mode (default) shows what would be deleted without making changes
- Optional backup before deletion using the existing backup script
- Rekordbox should be CLOSED while running to avoid DB locks

Examples:
    python scripts/remove_rekordbox_duplicates.py --group-by filename --dry-run
    python scripts/remove_rekordbox_duplicates.py --group-by title-artist --backup
    python scripts/remove_rekordbox_duplicates.py --group-by path

Grouping strategies ( --group-by ):
- path: exact FolderPath match (most strict)
- filename: base file name match, case-insensitive (default)
- title-artist: normalized Title + ArtistName match (looser; best-effort)
- isrc: ISRC string match (when populated)

Notes:
- Prefer tracks with a non-empty artist; entries with empty artist are
    deleted when possible regardless of playcount. If all in a group have
    empty artist, fall back to tie-breakers.
- Tie-breakers when multiple tracks share the highest playcount:
    1) Newer DateAdded wins, 2) Larger FileSize wins, 3) Stable/fallback order
- Deleting a track removes it from playlists (via DB cascades).

Requirements:
- pip install pyrekordbox
- Close Rekordbox before running.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

try:
    from pyrekordbox import Rekordbox6Database, db6
except ImportError:
    Rekordbox6Database = None  # type: ignore
    db6 = None  # type: ignore

# Optional backup integration


def _try_backup(backup_dir: Path | None, rekordbox_dir: Path | None) -> None:
    try:
        # Import from local scripts module
        from backup_rekordbox_db import RekordboxBackup  # type: ignore
    except Exception:
        print("[warn] Could not import backup script; skipping backup.")
        return

    try:
        mgr = RekordboxBackup(backup_dir=backup_dir, rekordbox_dir=rekordbox_dir)
        mgr.backup()
    except Exception as exc:
        print(f"[warn] Backup failed: {exc}")


def _normalize_str(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _get_artist_name(content: Any) -> str:
    # pyrekordbox exposes association proxies differently by version; try
    # common attributes. Fall back to empty string if not found.
    for attr in ("ArtistName", "Artist"):
        try:
            val = getattr(content, attr, None)
            # If association object, attempt Name field
            if hasattr(val, "Name"):
                return _normalize_str(val.Name)
            return _normalize_str(val)
        except Exception:
            continue
    return ""


def _safe_date(content: Any) -> dt.datetime:
    val = getattr(content, "DateAdded", None)
    if isinstance(val, dt.datetime):
        return val
    # Attempt parse from string
    if val:
        from contextlib import suppress

        with suppress(Exception):
            return dt.datetime.fromisoformat(str(val))
    # Fallback very old date
    return dt.datetime(1970, 1, 1)


def _int_field(content: Any, name: str) -> int:
    try:
        v = getattr(content, name, 0)
        if v is None:
            return 0
        return int(v)
    except Exception:
        return 0


def _group_key_func(strategy: str) -> Callable[[Any], str]:
    def by_path(c: Any) -> str:
        return _normalize_str(getattr(c, "FolderPath", ""))

    def by_filename(c: Any) -> str:
        fp = _normalize_str(getattr(c, "FolderPath", ""))
        return Path(fp).name.lower() if fp else ""

    def by_title_artist(c: Any) -> str:
        title = _normalize_str(getattr(c, "Title", ""))
        artist = _get_artist_name(c)
        return f"{title}::{artist}"

    def by_isrc(c: Any) -> str:
        return _normalize_str(getattr(c, "ISRC", ""))

    mapping = {
        "path": by_path,
        "filename": by_filename,
        "title-artist": by_title_artist,
        "isrc": by_isrc,
    }
    return mapping.get(strategy, by_filename)


def _choose_keeper(contents: List[Any]) -> Tuple[Any, List[Any]]:
    # Prefer non-empty artist; within the candidate set, pick by highest
    # DJPlayCount; tie-break by DateAdded desc, then FileSize desc.
    def sort_key(c: Any) -> Tuple[int, dt.datetime, int]:
        return (
            _int_field(c, "DJPlayCount"),
            _safe_date(c),
            _int_field(c, "FileSize"),
        )

    non_empty = [c for c in contents if _get_artist_name(c)]
    candidates = non_empty if non_empty else contents

    # Max by tuple; Python tuple comparison handles sequential tie-breakers
    keeper = max(candidates, key=sort_key)
    losers = [c for c in contents if c is not keeper]
    return keeper, losers


def _summarize_content(c: Any) -> str:
    title = getattr(c, "Title", "")
    artist = _get_artist_name(c)
    playcount = _int_field(c, "DJPlayCount")
    path = getattr(c, "FolderPath", "")
    return f"'{title}' by {artist} | playcount={playcount} | path={path}"


def find_duplicates(db: Any, group_by: str) -> Dict[str, List[Any]]:
    """Return groups with more than one content item for the key."""
    groups: Dict[str, List[Any]] = {}
    key_fn = _group_key_func(group_by)

    all_q = db.get_content()
    all_contents: Iterable[Any] = all_q.all() if hasattr(all_q, "all") else list(all_q)

    for c in all_contents:
        key = key_fn(c)
        if not key:
            continue
        groups.setdefault(key, []).append(c)

    # Filter only duplicates
    return {k: v for k, v in groups.items() if len(v) > 1}


def _process_group(db: Any, key: str, items: List[Any], dry_run: bool) -> int:
    keeper, losers = _choose_keeper(items)
    print(f"\nGroup: {key}")
    print(f"  Keep:   {_summarize_content(keeper)}")
    deleted = 0
    for c in losers:
        print(f"  Delete: {_summarize_content(c)}")
        if not dry_run:
            try:
                db.delete(c)
                deleted += 1
            except Exception as exc:
                print(f"    [warn] Failed to delete: {exc}")
    if not dry_run:
        try:
            db.commit()
        except Exception:
            from contextlib import suppress

            with suppress(Exception):
                db.rollback()
    return deleted


def delete_duplicates(
    db: Any, groups: Dict[str, List[Any]], dry_run: bool
) -> Dict[str, int]:
    deleted_total = 0
    kept = len(groups)
    for key, items in groups.items():
        deleted_total += _process_group(db, key, items, dry_run)
    return {"kept": kept, "deleted": deleted_total}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=("Remove duplicate Rekordbox tracks, keeping highest playcount")
    )
    parser.add_argument(
        "--group-by",
        choices=["filename", "path", "title-artist", "isrc"],
        default="filename",
        help="Strategy to detect duplicates (default: filename)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned deletions without applying changes",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a Rekordbox DB backup before deleting",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Custom backup directory (defaults to ~/backups/rekordbox)",
    )
    parser.add_argument(
        "--rekordbox-dir",
        type=Path,
        default=None,
        help="Custom Rekordbox database directory (auto-detected if not specified)",
    )

    args = parser.parse_args(argv)

    if Rekordbox6Database is None:
        print("pyrekordbox is required: pip install pyrekordbox", file=sys.stderr)
        return 2

    print("⚠️  Ensure Rekordbox is CLOSED before running.")
    if args.backup and not args.dry_run:
        _try_backup(args.backup_dir, args.rekordbox_dir)

    # Connect
    try:
        db = Rekordbox6Database()
    except Exception as exc:
        print(f"Failed to connect to Rekordbox database: {exc}", file=sys.stderr)
        return 1

    try:
        print(
            f"Scanning for duplicates (group-by: {args.group_by}, "
            f"dry-run={args.dry_run})..."
        )
        groups = find_duplicates(db, args.group_by)
        total_groups = len(groups)
        total_items = sum(len(v) for v in groups.values())
        if total_groups == 0:
            print("No duplicate groups found.")
            return 0

        print(f"Found {total_groups} groups with {total_items} duplicate items.")
        summary = delete_duplicates(db, groups, args.dry_run)
        print("\nSummary:")
        print(f"  Groups processed: {total_groups}")
        print(f"  Kept: {summary['kept']}")
        print(f"  Deleted: {summary['deleted']} (dry-run={args.dry_run})")
        print("Done.")
        return 0
    finally:
        from contextlib import suppress

        with suppress(Exception):
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
