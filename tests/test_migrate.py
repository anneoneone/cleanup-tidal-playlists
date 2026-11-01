import json
import sqlite3
import stat
from contextlib import closing
from pathlib import Path

import pytest

from cratekeeper.db import Database, Playlist, Track, head_revision
from cratekeeper.home import Home
from cratekeeper.migrate import MigrateError, migrate
from cratekeeper.settings import Settings

V1_SCHEMA = Path(__file__).parent / "data" / "v1_schema.sql"
NOW = "'2025-01-01'"


def make_v1(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(V1_SCHEMA.read_text())
        conn.execute("INSERT INTO alembic_version VALUES ('879cb3821a06')")
        conn.execute(
            "INSERT INTO playlists (id, source, name, sync_status, created_at, "
            "updated_at, track_count_tidal, track_count_local, track_count_rekordbox,"
            " tidal_id, last_updated_tidal) VALUES (1, 'tidal', 'House', 'unknown', "
            f"{NOW}, {NOW}, 0, 0, 0, 'p1', {NOW})"
        )
        tracks = [
            (1, "'t1'", "'[\"Playlists/House/a.mp3\"]'"),  # Tidal track, in playlist
            (2, "NULL", "'[\"Playlists/House/a.mp3\"]'"),  # local dup, in playlist
            (3, "NULL", "'[\"Playlists/House/b.mp3\"]'"),  # local, in no playlist
            (4, "'t4'", "NULL"),  # Tidal, in no playlist: kept
        ]
        for track_id, tidal_id, paths in tracks:
            conn.execute(
                "INSERT INTO tracks (id, tidal_id, title, artist, normalized_name, "
                "file_paths, download_status, tidal_unavailable, created_at, "
                f"updated_at) VALUES ({track_id}, {tidal_id}, 'T', 'A', 'a - t', "
                f"{paths}, 'downloaded', 0, {NOW}, {NOW})"
            )
        for row_id, track_id in ((1, 1), (2, 2)):
            conn.execute(
                "INSERT INTO playlist_tracks (id, playlist_id, track_id, in_tidal, "
                "in_local, in_rekordbox, sync_status, created_at, updated_at) VALUES "
                f"({row_id}, 1, {track_id}, 1, 1, 1, 'unknown', {NOW}, {NOW})"
            )
        conn.commit()


@pytest.fixture
def v1(isolated_home: Path) -> Path:
    db = isolated_home / ".tidal-cleanup" / "sync.db"
    make_v1(db)
    token = isolated_home / "Documents" / "tidal_session.json"
    token.parent.mkdir()
    token.write_text(json.dumps({"access_token": "a", "refresh_token": "r"}))
    settings = isolated_home / ".config" / "tidal_dl_ng" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"quality_audio": "HIGH"}))
    return db


def test_migrate_imports_cleans_and_writes_settings(
    v1: Path, tmp_path: Path, isolated_home: Path
) -> None:
    before = v1.read_bytes()
    env = tmp_path / ".env-Tidal"
    env.write_text(
        "# v1 settings\nTIDAL_CLEANUP_MP3_DIRECTORY=/Volumes/HDD/mp3\n"
        "TIDAL_CLEANUP_FFMPEG_QUALITY=0\n"
    )
    home = Home.resolve()

    report = migrate(home, env_file=env)

    assert v1.read_bytes() == before  # v1 untouched
    assert (report.playlists, report.orphan_tracks_removed) == (1, 1)
    assert report.shared_paths_fixed == 1
    db = Database(home.db_file)
    assert db.schema_revision() == head_revision()
    with db.session() as s:
        assert sorted(t.id for t in s.query(Track)) == [1, 2, 4]
        assert s.get(Track, 1).file_paths == ["Playlists/House/a.mp3"]
        assert s.get(Track, 2).file_paths == []
        playlist = s.get(Playlist, 1)
        assert playlist.last_updated_tidal is None and playlist.in_tidal is True
    settings = Settings.load(home)
    assert settings.music_folder == Path("/Volumes/HDD/mp3")
    assert settings.ffmpeg_quality == 0
    assert settings.download_quality == "HIGH"
    assert stat.S_IMODE(home.tidal_session_file.stat().st_mode) == 0o600


def test_migrate_refuses_existing_data_unless_forced(v1: Path) -> None:
    home = Home.resolve()
    migrate(home)
    with pytest.raises(MigrateError, match="--force"):
        migrate(home)
    assert migrate(home, force=True).playlists == 1


def test_migrate_needs_v1_database(tmp_path: Path) -> None:
    with pytest.raises(MigrateError, match="No v1 database"):
        migrate(Home.resolve(), v1_db=tmp_path / "missing.db")
