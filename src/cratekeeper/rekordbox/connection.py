"""Opening the Rekordbox library safely.

- Plans are made on a temporary copy, so planning never writes to (or locks)
  the live library.
- Writes refuse while Rekordbox runs.
- ``commit_changes`` mirrors pyrekordbox's ``commit`` but reports an XML save
  problem after the database commit as a warning instead of an error.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from pyrekordbox import Rekordbox6Database
from pyrekordbox.config import get_config
from pyrekordbox.db6 import tables
from pyrekordbox.utils import get_rekordbox_pid
from sqlalchemy import func

logger = logging.getLogger(__name__)

# pyrekordbox writes date values through sqlite3's default adapters, which are
# deprecated since Python 3.12 and warn on every use. These do the same thing.
sqlite3.register_adapter(date, lambda value: value.isoformat())
sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))

XML_NAME = "masterPlaylists6.xml"
SQLITE_HEADER = b"SQLite format 3\x00"
DB_SIDE_FILES = ("-wal", "-shm")


class RekordboxError(RuntimeError):
    """Raised for Rekordbox problems the user has to fix."""


class RekordboxRunningError(RekordboxError):
    """Raised when a write is attempted while Rekordbox is open."""


@dataclass(frozen=True)
class RekordboxLocation:
    """Where the library is."""

    db_path: Path

    @property
    def db_dir(self) -> Path:
        """Return the folder with ``master.db`` and ``masterPlaylists6.xml``."""
        return self.db_path.parent

    @property
    def xml_path(self) -> Path:
        """Return the playlist XML that Rekordbox keeps next to the database."""
        return self.db_dir / XML_NAME


def locate(configured: Optional[Path]) -> RekordboxLocation:
    """Return the configured library, or the one Rekordbox itself uses."""
    if configured is not None:
        path = configured
    else:
        config = get_config("rekordbox7") or get_config("rekordbox6") or {}
        raw = config.get("db_path") if hasattr(config, "get") else None
        if not raw:
            raise RekordboxError("No Rekordbox library found. Set rekordbox_db.")
        path = Path(raw)
    if not path.is_file():
        raise RekordboxError(f"Rekordbox library not found: {path}")
    return RekordboxLocation(db_path=path)


def rekordbox_running() -> bool:
    """Return whether the Rekordbox app is running."""
    return bool(get_rekordbox_pid())


def require_closed() -> None:
    """Raise :class:`RekordboxRunningError` if Rekordbox is running."""
    if rekordbox_running():
        raise RekordboxRunningError("Rekordbox is running. Close it and try again.")


def is_encrypted(db_path: Path) -> bool:
    """Return whether the database file is encrypted (real Rekordbox libraries are)."""
    with db_path.open("rb") as handle:
        return handle.read(len(SQLITE_HEADER)) != SQLITE_HEADER


def open_library(db_path: Path) -> Any:
    """Open a library file with pyrekordbox."""
    _install_string_sortkey()
    return Rekordbox6Database(db_path, unlock=is_encrypted(db_path))


@contextmanager
def planning_copy(location: RekordboxLocation) -> Iterator[Any]:
    """Open a temporary copy of the library (with its XML) for read-only work."""
    with tempfile.TemporaryDirectory(prefix="cratekeeper-plan-") as tmp:
        tmp_dir = Path(tmp)
        copy = tmp_dir / location.db_path.name
        shutil.copy2(location.db_path, copy)
        for suffix in DB_SIDE_FILES:
            side = Path(f"{location.db_path}{suffix}")
            if side.exists():
                shutil.copy2(side, Path(f"{copy}{suffix}"))
        if location.xml_path.exists():
            shutil.copy2(location.xml_path, tmp_dir / XML_NAME)
        database = open_library(copy)
        try:
            yield database
        finally:
            database.close()


def fingerprint(database: Any) -> str:
    """Return a value that changes whenever Rekordbox's playlists change."""
    usn = database.get_local_usn()
    playlists = database.session.query(func.max(tables.DjmdPlaylist.updated_at))
    songs = database.session.query(func.max(tables.DjmdSongPlaylist.updated_at))
    count = database.session.query(func.count(tables.DjmdSongPlaylist.ID))
    return f"{usn}|{playlists.scalar()}|{songs.scalar()}|{count.scalar()}"


def commit_changes(database: Any) -> Optional[str]:
    """Commit pending changes.

    Returns a warning if only the XML update failed.
    """
    require_closed()
    coerce_pending_ids(database)
    database.registry.autoincrement_local_update_count(set_row_usn=True)
    database.session.commit()
    database.registry.clear_buffer()
    xml = database.playlist_xml
    if xml is None:
        return None
    try:
        for playlist in database.get_playlist():
            node = xml.get(playlist.ID)
            drift = (
                abs((playlist.updated_at - node["Timestamp"]).total_seconds())
                if node is not None
                else 0
            )
            if drift > 1:
                xml.update(playlist.ID, updated_at=playlist.updated_at)
        if xml.modified:
            xml.save()
    except Exception as exc:  # the database commit already happened
        logger.warning("Rekordbox playlist XML not updated: %s", exc)
        return f"{XML_NAME} could not be updated: {exc}"
    return None


def coerce_pending_ids(database: Any) -> None:
    """Store new IDs as strings (pyrekordbox mixes int and str IDs; v1 fix)."""
    session = database.session
    for obj in list(session.new) + list(session.dirty):
        mapper = getattr(obj, "__mapper__", None)
        if mapper is None:
            continue
        for column in mapper.columns:
            if column.key == "ID" or column.key.endswith("ID"):
                value = getattr(obj, column.key, None)
                if isinstance(value, int) and not isinstance(value, bool):
                    setattr(obj, column.key, str(value))


def _install_string_sortkey() -> None:
    """Sort identities as strings during flush (int/str IDs cannot be compared)."""

    def string_sortkey(state: Any) -> tuple[str, ...]:
        key = state.key
        if not key:
            return ()
        return tuple(str(value) for value in key[1])

    for mapper in tables.Base.registry.mappers:
        if not getattr(mapper, "_cratekeeper_sortkey", False):
            mapper._persistent_sortkey_fn = string_sortkey
            mapper._cratekeeper_sortkey = True
