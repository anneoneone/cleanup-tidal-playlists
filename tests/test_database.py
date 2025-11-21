"""Tests for database models and service."""

import tempfile
from pathlib import Path

import pytest

from src.tidal_cleanup.database.models import Playlist, Track
from src.tidal_cleanup.database.service import DatabaseService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        db_service = DatabaseService(db_path)
        db_service.init_db()
        yield db_service
        db_service.close()


class TestDatabaseModels:
    """Test database models."""

    def test_track_model_creation(self):
        """Test Track model creation."""
        track = Track(
            tidal_id="123456",
            title="Test Track",
            artist="Test Artist",
            album="Test Album",
            year=2024,
            normalized_name="test artist - test track",
        )
        assert track.title == "Test Track"
        assert track.artist == "Test Artist"
        assert track.tidal_id == "123456"

    def test_playlist_model_creation(self):
        """Test Playlist model creation."""
        playlist = Playlist(
            tidal_id="pl123",
            name="Test Playlist",
            description="A test playlist",
        )
        assert playlist.name == "Test Playlist"
        assert playlist.tidal_id == "pl123"


class TestDatabaseService:
    """Test database service operations."""

    def test_init_db(self, temp_db):
        """Test database initialization."""
        assert temp_db.db_path.exists()
        stats = temp_db.get_statistics()
        assert stats["tracks"] == 0
        assert stats["playlists"] == 0

    def test_create_track(self, temp_db):
        """Test creating a track."""
        track_data = {
            "tidal_id": "123456",
            "title": "Test Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "year": 2024,
        }
        track = temp_db.create_track(track_data)
        assert track.id is not None
        assert track.title == "Test Track"
        assert track.normalized_name is not None

    def test_get_track_by_tidal_id(self, temp_db):
        """Test retrieving track by Tidal ID."""
        track_data = {
            "tidal_id": "123456",
            "title": "Test Track",
            "artist": "Test Artist",
        }
        created_track = temp_db.create_track(track_data)

        retrieved_track = temp_db.get_track_by_tidal_id("123456")
        assert retrieved_track is not None
        assert retrieved_track.id == created_track.id
        assert retrieved_track.title == "Test Track"

    def test_create_or_update_track(self, temp_db):
        """Test create or update track logic."""
        track_data = {
            "tidal_id": "123456",
            "title": "Test Track",
            "artist": "Test Artist",
        }

        # Create
        track1 = temp_db.create_or_update_track(track_data)
        assert track1.id is not None

        # Update with same tidal_id
        track_data["album"] = "New Album"
        track2 = temp_db.create_or_update_track(track_data)
        assert track2.id == track1.id
        assert track2.album == "New Album"

        # Verify only one track exists
        stats = temp_db.get_statistics()
        assert stats["tracks"] == 1

    def test_create_playlist(self, temp_db):
        """Test creating a playlist."""
        playlist_data = {
            "tidal_id": "pl123",
            "name": "Test Playlist",
            "description": "A test playlist",
        }
        playlist = temp_db.create_playlist(playlist_data)
        assert playlist.id is not None
        assert playlist.name == "Test Playlist"

    def test_get_playlist_by_tidal_id(self, temp_db):
        """Test retrieving playlist by Tidal ID."""
        playlist_data = {
            "tidal_id": "pl123",
            "name": "Test Playlist",
        }
        created_playlist = temp_db.create_playlist(playlist_data)

        retrieved_playlist = temp_db.get_playlist_by_tidal_id("pl123")
        assert retrieved_playlist is not None
        assert retrieved_playlist.id == created_playlist.id

    def test_add_track_to_playlist(self, temp_db):
        """Test adding track to playlist."""
        # Create track and playlist
        track = temp_db.create_track(
            {"tidal_id": "123", "title": "Track 1", "artist": "Artist 1"}
        )
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})

        # Add track to playlist
        playlist_track = temp_db.add_track_to_playlist(
            playlist.id, track.id, position=1, in_tidal=True
        )

        assert playlist_track is not None
        assert playlist_track.playlist_id == playlist.id
        assert playlist_track.track_id == track.id
        assert playlist_track.position == 1
        assert playlist_track.in_tidal is True

    def test_get_playlist_tracks(self, temp_db):
        """Test retrieving tracks from a playlist."""
        # Create playlist
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})

        # Create and add tracks
        track1 = temp_db.create_track(
            {"tidal_id": "123", "title": "Track 1", "artist": "Artist 1"}
        )
        track2 = temp_db.create_track(
            {"tidal_id": "456", "title": "Track 2", "artist": "Artist 2"}
        )

        temp_db.add_track_to_playlist(playlist.id, track1.id, position=1, in_tidal=True)
        temp_db.add_track_to_playlist(playlist.id, track2.id, position=2, in_tidal=True)

        # Retrieve tracks
        tracks = temp_db.get_playlist_tracks(playlist.id)
        assert len(tracks) == 2
        assert tracks[0].title == "Track 1"
        assert tracks[1].title == "Track 2"

    def test_remove_track_from_playlist(self, temp_db):
        """Test removing track from playlist."""
        # Create and link track and playlist
        track = temp_db.create_track(
            {"tidal_id": "123", "title": "Track 1", "artist": "Artist 1"}
        )
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})
        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_tidal=True)

        # Remove track
        result = temp_db.remove_track_from_playlist(
            playlist.id, track.id, source="tidal"
        )
        assert result is True

        # Verify removal
        tracks = temp_db.get_playlist_tracks(playlist.id)
        assert len(tracks) == 0

    def test_create_sync_operation(self, temp_db):
        """Test creating sync operation."""
        operation_data = {
            "operation_type": "download",
            "status": "pending",
            "action": "add",
            "source": "tidal",
            "target": "local",
        }
        operation = temp_db.create_sync_operation(operation_data)
        assert operation.id is not None
        assert operation.status == "pending"

    def test_get_pending_operations(self, temp_db):
        """Test retrieving pending operations."""
        # Create operations
        temp_db.create_sync_operation(
            {
                "operation_type": "download",
                "status": "pending",
            }
        )
        temp_db.create_sync_operation(
            {
                "operation_type": "sync",
                "status": "completed",
            }
        )

        pending = temp_db.get_pending_operations()
        assert len(pending) == 1
        assert pending[0].status == "pending"

    def test_update_operation_status(self, temp_db):
        """Test updating operation status."""
        operation = temp_db.create_sync_operation(
            {
                "operation_type": "download",
                "status": "pending",
            }
        )

        # Update to running
        updated = temp_db.update_operation_status(operation.id, "running")
        assert updated.status == "running"
        assert updated.started_at is not None

        # Update to completed
        completed = temp_db.update_operation_status(operation.id, "completed")
        assert completed.status == "completed"
        assert completed.completed_at is not None

    def test_create_snapshot(self, temp_db):
        """Test creating a snapshot."""
        snapshot_data = {
            "playlist_count": 10,
            "track_count": 100,
            "playlists": [],
        }
        snapshot = temp_db.create_snapshot("tidal", snapshot_data)
        assert snapshot.id is not None
        assert snapshot.snapshot_type == "tidal"
        assert snapshot.playlist_count == 10

    def test_get_latest_snapshot(self, temp_db):
        """Test retrieving latest snapshot."""
        # Create multiple snapshots
        temp_db.create_snapshot("tidal", {"playlist_count": 5})
        temp_db.create_snapshot("tidal", {"playlist_count": 10})

        latest = temp_db.get_latest_snapshot("tidal")
        assert latest is not None
        assert latest.playlist_count == 10

    def test_normalize_track_name(self):
        """Test track name normalization."""
        normalized = DatabaseService._normalize_track_name(
            "Track Title (Remix)", "Artist Name feat. Someone"
        )
        assert "artist name" in normalized.lower()
        assert "track title" in normalized.lower()
        assert "feat" not in normalized.lower()
        assert "remix" not in normalized.lower()

    def test_get_statistics(self, temp_db):
        """Test getting database statistics."""
        # Add some data
        temp_db.create_track(
            {"tidal_id": "123", "title": "Track 1", "artist": "Artist 1"}
        )
        temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})

        stats = temp_db.get_statistics()
        assert stats["tracks"] == 1
        assert stats["playlists"] == 1
        assert "database_path" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
