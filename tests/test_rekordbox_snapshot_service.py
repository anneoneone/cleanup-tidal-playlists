"""Tests for Rekordbox snapshot synchronization."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

from src.tidal_cleanup.core.rekordbox.snapshot_service import RekordboxSnapshotService
from src.tidal_cleanup.database.service import DatabaseService


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    service = DatabaseService(db_path)
    service.init_db()
    yield service
    service.close()


@pytest.fixture
def mp3_root(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    return root


@pytest.fixture
def config(mp3_root):
    return SimpleNamespace(mp3_directory=str(mp3_root))


@pytest.fixture
def rekordbox_service():
    return FakeRekordboxService(FakeRekordboxDB())


class QueryStub:
    def __init__(self, result: Optional[Any]):
        """Initialize stub query wrapper."""
        self._result = result

    def first(self) -> Optional[Any]:
        return self._result


class FakeContent:
    def __init__(self, content_id: int, path: str):
        """Initialize fake Rekordbox content."""
        self.ID = str(content_id)
        self.FolderPath = path


class FakeSong:
    def __init__(self, content: FakeContent):
        """Initialize fake Rekordbox song wrapper."""
        self.Content = content


class FakePlaylist:
    def __init__(self, playlist_id: int, name: str):
        """Initialize fake playlist entry."""
        self.ID = str(playlist_id)
        self.Name = name
        self.Songs = []


class FakeRekordboxDB:
    def __init__(self) -> None:
        """Prepare in-memory Rekordbox-like storage."""
        self.playlists: Dict[str, FakePlaylist] = {}
        self.contents: Dict[str, FakeContent] = {}
        self._next_playlist_id = 1
        self._next_content_id = 1

    def create_playlist(self, name: str) -> FakePlaylist:
        playlist = FakePlaylist(self._next_playlist_id, name)
        self.playlists[playlist.ID] = playlist
        self._next_playlist_id += 1
        return playlist

    def get_playlist(self, **filters: Any) -> QueryStub:
        if "ID" in filters:
            return QueryStub(self.playlists.get(str(filters["ID"])))
        if "Name" in filters:
            for playlist in self.playlists.values():
                if playlist.Name == filters["Name"]:
                    return QueryStub(playlist)
            return QueryStub(None)
        return QueryStub(None)

    def add_to_playlist(self, playlist: FakePlaylist, content: FakeContent) -> None:
        playlist.Songs.append(FakeSong(content))

    def remove_from_playlist(self, playlist: FakePlaylist, song: FakeSong) -> None:
        if song in playlist.Songs:
            playlist.Songs.remove(song)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def get_content(self, **filters: Any) -> QueryStub:
        path = filters.get("FolderPath")
        return QueryStub(self.contents.get(path))

    def add_content(self, folder_path: str) -> FakeContent:
        content = FakeContent(self._next_content_id, folder_path)
        self.contents[folder_path] = content
        self._next_content_id += 1
        return content


class FakeRekordboxService:
    def __init__(self, db: FakeRekordboxDB):
        """Initialize fake Rekordbox service facade."""
        self.db = db

    def get_or_create_content(self, track_path: Path) -> FakeContent:
        existing = self.db.get_content(FolderPath=str(track_path)).first()
        if existing:
            return existing
        return self.db.add_content(str(track_path))

    def refresh_playlist(self, playlist: FakePlaylist) -> FakePlaylist:
        return self.db.playlists.get(playlist.ID, playlist)


def test_sync_creates_rekordbox_playlist_and_tracks(temp_db, rekordbox_service, config):
    playlist = temp_db.create_playlist({"name": "Playlist 1", "tidal_id": "tidal"})
    track_path = Path(config.mp3_directory) / "Playlist 1" / "Track 1.mp3"
    track_path.parent.mkdir(parents=True, exist_ok=True)
    track_path.write_text("audio")

    track = temp_db.create_track(
        {
            "title": "Track 1",
            "artist": "Artist",
            "file_path": str(Path("Playlist 1") / "Track 1.mp3"),
        }
    )
    temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_local=True)

    service = RekordboxSnapshotService(rekordbox_service, temp_db, config)
    summary = service.sync_database_to_rekordbox()

    assert summary["playlists_processed"] == 1
    assert summary["playlists_created"] == 1
    assert summary["tracks_added"] == 1

    refreshed_playlist = temp_db.get_playlist_by_id(playlist.id)
    refreshed_track = temp_db.get_track_by_id(track.id)
    assert refreshed_playlist.rekordbox_playlist_id == "1"
    assert refreshed_track.rekordbox_content_id == "1"


def test_sync_prunes_extra_tracks(temp_db, config):
    fake_db = FakeRekordboxDB()
    rekordbox_service = FakeRekordboxService(fake_db)

    playlist = temp_db.create_playlist({"name": "Playlist 1", "tidal_id": "tidal"})
    track_path = Path(config.mp3_directory) / "Playlist 1" / "Track 1.mp3"
    track_path.parent.mkdir(parents=True, exist_ok=True)
    track_path.write_text("audio")

    track = temp_db.create_track(
        {
            "title": "Track 1",
            "artist": "Artist",
            "file_path": str(Path("Playlist 1") / "Track 1.mp3"),
        }
    )
    temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_local=True)

    rb_playlist = fake_db.create_playlist("Playlist 1")
    matching_content = fake_db.add_content(str(track_path))
    extra_content_path = Path(config.mp3_directory) / "Playlist 1" / "Extra.mp3"
    extra_content_path.write_text("extra")
    extra_content = fake_db.add_content(str(extra_content_path))

    rb_playlist.Songs.append(FakeSong(matching_content))
    rb_playlist.Songs.append(FakeSong(extra_content))

    temp_db.set_playlist_rekordbox_id(playlist.id, rb_playlist.ID)
    temp_db.set_track_rekordbox_id(track.id, matching_content.ID)

    service = RekordboxSnapshotService(rekordbox_service, temp_db, config)
    summary = service.sync_database_to_rekordbox(prune_extra=True)

    assert summary["tracks_removed"] == 1
    assert len(fake_db.playlists[rb_playlist.ID].Songs) == 1


def test_sync_uses_symlink_path_when_track_missing_file(temp_db, config):
    fake_db = FakeRekordboxDB()
    rekordbox_service = FakeRekordboxService(fake_db)

    playlist = temp_db.create_playlist({"name": "Python", "tidal_id": "pl"})
    actual_dir = Path(config.mp3_directory) / "Shared" / "Color"
    actual_dir.mkdir(parents=True, exist_ok=True)
    actual_path = actual_dir / "Fun Fun - Color My Love.m4a"
    actual_path.write_text("audio")

    playlist_dir = Path(config.mp3_directory) / "Playlists" / playlist.name
    playlist_dir.mkdir(parents=True, exist_ok=True)
    symlink_path = playlist_dir / "Fun Fun - Color My Love.m4a"
    symlink_path.symlink_to(actual_path)

    track = temp_db.create_track({"title": "Color My Love", "artist": "Fun Fun"})
    temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_local=True)
    temp_db.update_symlink_status(playlist.id, track.id, str(symlink_path), True)

    service = RekordboxSnapshotService(rekordbox_service, temp_db, config)
    summary = service.sync_database_to_rekordbox()

    assert summary["tracks_added"] == 1
    refreshed_track = temp_db.get_track_by_id(track.id)
    assert refreshed_track.rekordbox_content_id == "1"
    assert str(actual_path) in fake_db.contents
