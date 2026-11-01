"""Backups of Cratekeeper's database and the Rekordbox library files.

A full Backup (before every Apply) holds the database and Rekordbox's
``master.db`` (+ ``-wal``/``-shm``), ``local.db`` and ``masterPlaylists6.xml``.
A database-only Backup is taken before every Refresh. Both kinds have their own
retention, so frequent database Backups never push out the last library copy.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from .db.engine import Database
from .home import Home
from .rekordbox.connection import XML_NAME, RekordboxLocation, require_closed

logger = logging.getLogger(__name__)

BackupKind = Literal["full", "db"]
_ID = re.compile(r"^\d{8}-\d{6}-\d{2}-[a-z0-9-]+$")
REKORDBOX_FILES = ("master.db", "master.db-wal", "master.db-shm", "local.db", XML_NAME)
DB_FILE = "cratekeeper.db"


class BackupError(RuntimeError):
    """Raised when a Backup cannot be made or restored."""


@dataclass
class BackupInfo:
    """What a Backup folder holds (stored as ``meta.json``)."""

    id: str
    kind: BackupKind
    label: str
    created_at: str
    rekordbox_dir: Optional[str] = None
    files: list[str] = field(default_factory=list)
    size_bytes: int = 0


def create_backup(
    home: Home,
    db: Database,
    label: str,
    rekordbox: Optional[RekordboxLocation] = None,
    keep_full: int = 20,
    keep_db: int = 10,
) -> BackupInfo:
    """Make a Backup.

    With ``rekordbox`` it is a full Backup.
    """
    home.backups_dir.mkdir(parents=True, exist_ok=True)
    folder = _new_folder(home, label)
    kind: BackupKind = "full" if rekordbox is not None else "db"
    files: list[str] = []
    try:
        _copy_sqlite(db.path, folder / DB_FILE)
        files.append(DB_FILE)
        if rekordbox is not None:
            for name in REKORDBOX_FILES:
                source = rekordbox.db_dir / name
                if source.exists():
                    shutil.copy2(source, folder / name)
                    files.append(name)
            if "master.db" not in files:
                raise BackupError(f"Rekordbox library not found in {rekordbox.db_dir}")
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    info = BackupInfo(
        id=folder.name,
        kind=kind,
        label=label,
        created_at=datetime.now().isoformat(timespec="seconds"),
        rekordbox_dir=str(rekordbox.db_dir) if rekordbox else None,
        files=files,
        size_bytes=sum((folder / f).stat().st_size for f in files),
    )
    (folder / "meta.json").write_text(json.dumps(asdict(info), indent=2))
    _prune(home, "full", keep_full)
    _prune(home, "db", keep_db)
    logger.info("Backup %s (%s) created", info.id, kind)
    return info


def list_backups(home: Home) -> list[BackupInfo]:
    """Return Backups, newest first."""
    if not home.backups_dir.is_dir():
        return []
    result = []
    for folder in home.backups_dir.iterdir():
        meta = folder / "meta.json"
        if folder.is_dir() and meta.is_file():
            try:
                result.append(BackupInfo(**json.loads(meta.read_text())))
            except (TypeError, ValueError):
                logger.warning("Ignoring unreadable backup %s", folder.name)
    return sorted(result, key=lambda b: b.id, reverse=True)


def get_backup(home: Home, backup_id: str) -> BackupInfo:
    """Return one Backup, after checking the ID cannot leave the backups folder."""
    if not _ID.match(backup_id):
        raise BackupError(f"Invalid backup ID: {backup_id!r}")
    for info in list_backups(home):
        if info.id == backup_id:
            return info
    raise BackupError(f"Backup {backup_id!r} not found")


def restore_backup(
    home: Home,
    db: Database,
    backup_id: str,
    keep_full: int = 20,
    keep_db: int = 10,
) -> BackupInfo:
    """Put a Backup back in place.

    A Backup of the current state is taken first.
    """
    info = get_backup(home, backup_id)
    folder = home.backups_dir / info.id
    target_dir = Path(info.rekordbox_dir) if info.rekordbox_dir else None
    if info.kind == "full":
        require_closed()
        if target_dir is None or not target_dir.is_dir():
            raise BackupError(f"Rekordbox folder not found: {info.rekordbox_dir}")
    current = (
        RekordboxLocation(db_path=target_dir / "master.db") if target_dir else None
    )
    create_backup(
        home, db, f"before-restore-{info.id[:15]}", current, keep_full, keep_db
    )

    db.dispose()
    _replace(folder / DB_FILE, db.path)
    if target_dir is not None:
        for side in ("master.db-wal", "master.db-shm"):
            if side not in info.files:
                (target_dir / side).unlink(missing_ok=True)
        for name in info.files:
            if name != DB_FILE:
                shutil.copy2(folder / name, target_dir / name)
    logger.info("Backup %s restored", info.id)
    return info


def _new_folder(home: Home, label: str) -> Path:
    """Return a new folder named ``<time>-<NN>-<label>``.

    The counter keeps IDs unique within one second and makes string order equal creation
    order.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "backup"
    taken = [p.name for p in home.backups_dir.glob(f"{stamp}-*")]
    counter = len(taken)
    while True:
        folder = home.backups_dir / f"{stamp}-{counter:02d}-{slug}"
        if not folder.exists():
            folder.mkdir()
            return folder
        counter += 1


def _copy_sqlite(source: Path, target: Path) -> None:
    """Copy a live SQLite database consistently (includes WAL contents).

    ``sqlite3.connect`` as a context manager does not close the connection, so
    both are closed explicitly: an open handle would break a later restore.
    """
    with (
        closing(sqlite3.connect(source)) as src,
        closing(sqlite3.connect(target)) as dst,
    ):
        src.backup(dst)


def _replace(source: Path, target: Path) -> None:
    for suffix in ("-wal", "-shm"):
        Path(f"{target}{suffix}").unlink(missing_ok=True)
    shutil.copy2(source, target)


def _prune(home: Home, kind: BackupKind, keep: int) -> None:
    backups = [b for b in list_backups(home) if b.kind == kind]
    for old in backups[keep:]:
        shutil.rmtree(home.backups_dir / old.id, ignore_errors=True)
        logger.info("Removed old backup %s", old.id)
