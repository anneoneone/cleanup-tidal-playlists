#!/usr/bin/env python3
"""Delete all tracks (content rows) from the Rekordbox database.

⚠️  This removes *every* track and associated content rows. Use only on a backup.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database, db6  # noqa: E402


def confirm_deletion() -> bool:
    """Prompt the user twice before performing destructive deletion."""
    print(
        "⚠️  WARNING: This will delete ALL tracks from Rekordbox, including cues, MyTags, playlists links, etc."
    )
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        return False
    return input("Type 'DELETE TRACKS' to confirm: ").strip() == "DELETE"


def _tables_with_column(column_name: str) -> Iterable:
    """Return all mapped tables that contain a given column name."""
    return [
        table
        for table in db6.tables.Base.metadata.tables.values()
        if column_name in table.c
    ]


def _row_count(session, table) -> int:
    """Get row count for a table."""
    result = session.execute(select(func.count()).select_from(table)).scalar()
    return int(result or 0)


def delete_all_tracks() -> int:
    rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"
    if not rekordbox_db.exists():
        print(f"❌ Rekordbox database not found: {rekordbox_db}")
        return 1

    if not confirm_deletion():
        print("❌ Cancelled.")
        return 0

    print("\n🔧 Opening Rekordbox database...")
    with Rekordbox6Database(rekordbox_db) as db:
        session = db.session

        ref_tables = [
            t for t in _tables_with_column("ContentID") if t.name != "djmdContent"
        ]
        ref_tables.sort(key=lambda t: t.name)
        content_table = db6.tables.Base.metadata.tables["djmdContent"]

        total_removed = 0

        print("\n🗑️  Deleting content-linked rows (playlists, cues, tags, etc.)...")
        for table in ref_tables:
            rows = _row_count(session, table)
            if rows:
                session.execute(table.delete())
                total_removed += rows
            print(f"  {table.name}: removed {rows}")

        content_rows = _row_count(session, content_table)
        print(f"\n🗑️  Deleting all content rows: {content_rows}")
        if content_rows:
            session.execute(content_table.delete())
            total_removed += content_rows

        print("\n💾 Committing changes...")
        session.commit()

        print(
            f"\n✅ Done. Removed ~{total_removed} rows across content and linked tables."
        )

    return 0


if __name__ == "__main__":
    sys.exit(delete_all_tracks())
