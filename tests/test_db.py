import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select, text

from cratekeeper.db import (
    Database,
    DatabaseError,
    PlaylistTrack,
    RunKind,
    RunStatus,
    Stick,
    StickTrack,
    head_revision,
)
from cratekeeper.db import repository as repo
from cratekeeper.db.engine import table_names

V1_SCHEMA = Path(__file__).parent / "data" / "v1_schema.sql"


def make_v1_database(path: Path) -> None:
    """Build a database with the exact schema of a live v1 install, plus rows."""
    with sqlite3.connect(path) as conn:
        conn.executescript(V1_SCHEMA.read_text())
        conn.execute("INSERT INTO alembic_version VALUES ('879cb3821a06')")
        conn.execute(
            "INSERT INTO playlists (id, source, name, sync_status, created_at, "
            "updated_at, track_count_tidal, track_count_local, track_count_rekordbox) "
            "VALUES (1, 'tidal', 'House', 'unknown', '2025-01-01', '2025-01-01', "
            "0, 0, 0)"
        )
        conn.execute(
            "INSERT INTO tracks (id, title, artist, normalized_name, download_status, "
            "tidal_unavailable, created_at, updated_at) VALUES (1, 'T', 'A', 'a - t', "
            "'downloaded', 0, '2025-01-01', '2025-01-01')"
        )
        conn.execute(
            "INSERT INTO playlist_tracks (id, playlist_id, track_id, in_tidal, "
            "in_local, in_rekordbox, sync_status, created_at, updated_at) VALUES "
            "(1, 1, 1, 1, 1, 1, 'unknown', '2025-01-01', '2025-01-01')"
        )


def test_new_database_is_created_at_head(tmp_path: Path) -> None:
    db = Database(tmp_path / "new.db")
    db.prepare()
    assert db.schema_revision() == head_revision()
    assert {"runs", "playlists", "tracks", "playlist_tracks"} <= set(
        table_names(db.engine)
    )


def test_connections_use_pragmas(tmp_path: Path) -> None:
    db = Database(tmp_path / "new.db")
    db.prepare()
    with db.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_v1_database_is_upgraded_and_keeps_rows(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    make_v1_database(path)
    db = Database(path)
    db.prepare()

    assert db.schema_revision() == head_revision()
    assert {"sticks", "stick_tracks"} <= set(table_names(db.engine))
    with db.session() as session:
        row = session.scalars(select(PlaylistTrack)).one()
        assert row.in_local is True
        assert row.in_bandcamp is False
        run = repo.start_run(session, RunKind.SYNC)
        assert run.id == 1


def test_prepare_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    make_v1_database(path)
    Database(path).prepare()
    Database(path).prepare()
    assert Database(path).schema_revision() == head_revision()


def test_tables_without_version_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "odd.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE something (id INTEGER)")
    with pytest.raises(DatabaseError, match="no migration version"):
        Database(path).prepare()


def test_non_sqlite_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "junk.db"
    path.write_bytes(b"not a database at all, just bytes" * 10)
    with pytest.raises(DatabaseError, match="not a SQLite database"):
        Database(path).prepare()


def test_session_rolls_back_on_error(tmp_path: Path) -> None:
    db = Database(tmp_path / "new.db")
    db.prepare()
    with pytest.raises(RuntimeError), db.session() as session:
        repo.start_run(session, RunKind.SYNC)
        raise RuntimeError("boom")
    with db.session() as session:
        assert repo.latest_run(session) is None


def test_run_lifecycle(tmp_path: Path) -> None:
    db = Database(tmp_path / "new.db")
    db.prepare()
    with db.session() as session:
        sync = repo.start_run(session, RunKind.SYNC, scope="House")
        sync_id = sync.id
    with db.session() as session:
        repo.finish_run(
            session, sync_id, RunStatus.SUCCEEDED, summary={"n": 1}, plan={"g": []}
        )
        apply = repo.start_run(session, RunKind.APPLY, plan_run_id=sync_id)
        apply_id = apply.id
    with db.session() as session:
        assert repo.mark_interrupted_runs(session) == 1
    with db.session() as session:
        runs = repo.list_runs(session)
        assert [r.id for r in runs] == [apply_id, sync_id]
        assert runs[0].status == RunStatus.FAILED.value
        assert runs[0].error and "Interrupted" in runs[0].error
        assert runs[1].plan == {"g": []}
        latest_sync = repo.latest_run(session, RunKind.SYNC)
        assert latest_sync is not None and latest_sync.scope == "House"
    with pytest.raises(LookupError), db.session() as session:
        repo.finish_run(session, 999, RunStatus.FAILED)


def test_library_counts_on_empty_db(tmp_path: Path) -> None:
    db = Database(tmp_path / "new.db")
    db.prepare()
    with db.session() as session:
        assert repo.library_counts(session) == {
            "playlists": 0,
            "tracks": 0,
            "tidal_tracks": 0,
            "tracks_in_rekordbox": 0,
        }


def test_upgraded_stick_tracks_go_with_their_track(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    make_v1_database(path)
    db = Database(path)
    db.prepare()
    with db.session() as session:
        session.add(Stick(id=1, volume_id="u1", name="S1", scanned_at=repo.utc_now()))
        session.flush()
        session.add(StickTrack(stick_id=1, track_id=1))
    with db.session() as session:
        session.execute(text("DELETE FROM tracks WHERE id = 1"))
    with db.session() as session:
        assert session.scalars(select(StickTrack)).all() == []
