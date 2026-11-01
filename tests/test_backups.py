from pathlib import Path

import pytest

import cratekeeper.rekordbox.connection as connection
from cratekeeper.backups import (
    BackupError,
    create_backup,
    get_backup,
    list_backups,
    restore_backup,
)
from cratekeeper.db import Database, Playlist
from cratekeeper.home import Home
from cratekeeper.rekordbox.connection import RekordboxLocation, RekordboxRunningError


@pytest.fixture
def home(tmp_path: Path) -> Home:
    return Home(root=tmp_path / "ck").ensure()


@pytest.fixture
def db(home: Home) -> Database:
    database = Database(home.db_file)
    database.prepare()
    return database


def playlist_names(db: Database) -> list[str]:
    with db.session() as s:
        return [p.name for p in s.query(Playlist).order_by(Playlist.name)]


def test_full_backup_contains_library_files(
    home: Home, db: Database, rekordbox_library: Path
) -> None:
    location = RekordboxLocation(db_path=rekordbox_library)
    info = create_backup(home, db, "Before apply", location)
    assert info.kind == "full"
    assert set(info.files) >= {"cratekeeper.db", "master.db", "masterPlaylists6.xml"}
    assert list_backups(home)[0].id == info.id
    assert info.id.endswith("-00-before-apply")


def test_retention_is_per_kind(
    home: Home, db: Database, rekordbox_library: Path
) -> None:
    location = RekordboxLocation(db_path=rekordbox_library)
    full = create_backup(home, db, "full", location, keep_full=1, keep_db=2)
    for i in range(4):
        create_backup(home, db, f"db {i}", keep_full=1, keep_db=2)
    kinds = [b.kind for b in list_backups(home)]
    assert kinds.count("db") == 2
    assert kinds.count("full") == 1
    assert get_backup(home, full.id).id == full.id


def test_restore_puts_database_and_library_back(
    home: Home, db: Database, rekordbox_library: Path
) -> None:
    location = RekordboxLocation(db_path=rekordbox_library)
    with db.session() as s:
        s.add(Playlist(name="Before"))
    info = create_backup(home, db, "snapshot", location)
    with db.session() as s:
        s.add(Playlist(name="After"))
    original_master = rekordbox_library.read_bytes()
    rekordbox_library.write_bytes(b"broken")
    stale = Path(f"{rekordbox_library}-wal")
    stale.write_bytes(b"stale wal")

    restore_backup(home, db, info.id)

    assert playlist_names(db) == ["Before"]
    assert rekordbox_library.read_bytes() == original_master
    assert not stale.exists()
    labels = [b.label for b in list_backups(home)]
    assert any(label.startswith("before-restore") for label in labels)


def test_restore_refuses_while_rekordbox_runs(
    home: Home,
    db: Database,
    rekordbox_library: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = create_backup(home, db, "x", RekordboxLocation(db_path=rekordbox_library))
    monkeypatch.setattr(connection, "get_rekordbox_pid", lambda: 99)
    with pytest.raises(RekordboxRunningError):
        restore_backup(home, db, info.id)


@pytest.mark.parametrize(
    "bad_id", ["../etc", "20260101-000000-00-../../x", "20260101-000000-x", "nope"]
)
def test_invalid_ids_are_rejected(home: Home, bad_id: str) -> None:
    with pytest.raises(BackupError):
        get_backup(home, bad_id)


def test_missing_library_aborts_full_backup(
    home: Home, db: Database, tmp_path: Path
) -> None:
    location = RekordboxLocation(db_path=tmp_path / "nowhere" / "master.db")
    with pytest.raises(BackupError, match="not found"):
        create_backup(home, db, "x", location)
    assert list_backups(home) == []


def test_ids_sort_in_creation_order_within_one_second(home: Home, db: Database) -> None:
    ids = [create_backup(home, db, f"b{i}").id for i in range(3)]
    assert [b.id for b in list_backups(home)] == list(reversed(ids))
