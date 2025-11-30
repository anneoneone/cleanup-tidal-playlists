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

    def test_set_playlist_rekordbox_id(self, temp_db):
        """Test storing Rekordbox playlist identifiers."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})

        updated = temp_db.set_playlist_rekordbox_id(playlist.id, "RB-42")
        assert updated is True

        refreshed = temp_db.get_playlist_by_id(playlist.id)
        assert refreshed is not None
        assert refreshed.rekordbox_playlist_id == "RB-42"

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

    def test_get_last_sync_timestamp(self, temp_db):
        """Test retrieving last sync timestamp."""
        # No snapshots yet
        timestamp = temp_db.get_last_sync_timestamp("tidal_sync")
        assert timestamp is None

        # Create first snapshot
        snapshot1 = temp_db.create_snapshot("tidal_sync", {"status": "completed"})
        timestamp1 = temp_db.get_last_sync_timestamp("tidal_sync")
        assert timestamp1 is not None
        assert timestamp1 == snapshot1.created_at

        # Create second snapshot (should be newer)
        snapshot2 = temp_db.create_snapshot("tidal_sync", {"status": "completed"})
        timestamp2 = temp_db.get_last_sync_timestamp("tidal_sync")
        assert timestamp2 is not None
        assert timestamp2 == snapshot2.created_at
        assert timestamp2 > timestamp1

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


class TestDatabaseServiceEdgeCases:
    """Test edge cases and error handling in database service."""

    def test_update_track_not_found(self, temp_db):
        """Test updating non-existent track raises ValueError."""
        with pytest.raises(ValueError, match="Track not found"):
            temp_db.update_track(99999, {"title": "New Title"})

    def test_update_playlist_not_found(self, temp_db):
        """Test updating non-existent playlist raises ValueError."""
        with pytest.raises(ValueError, match="Playlist not found"):
            temp_db.update_playlist(99999, {"name": "New Name"})

    def test_update_operation_status_not_found(self, temp_db):
        """Test updating non-existent operation raises ValueError."""
        with pytest.raises(ValueError, match="Operation not found"):
            temp_db.update_operation_status(99999, "completed")

    def test_create_or_update_track_by_file_path(self, temp_db):
        """Test create_or_update_track finds track by file_path."""
        # Create track with file_path
        track_data = {
            "tidal_id": "123",
            "title": "Test Track",
            "artist": "Test Artist",
            "file_path": "/music/test.mp3",
        }
        track1 = temp_db.create_track(track_data)

        # Update by file_path (no tidal_id match)
        track_data_update = {
            "tidal_id": "456",  # Different tidal_id
            "title": "Updated Track",
            "artist": "Test Artist",
            "file_path": "/music/test.mp3",  # Same file_path
        }
        track2 = temp_db.create_or_update_track(track_data_update)

        # Should update the same track
        assert track2.id == track1.id
        assert track2.title == "Updated Track"

    def test_create_or_update_track_by_metadata(self, temp_db):
        """Test create_or_update_track finds track by title/artist."""
        # Create track
        track_data = {
            "title": "Unique Title",
            "artist": "Unique Artist",
        }
        track1 = temp_db.create_track(track_data)

        # Update by metadata (no tidal_id or file_path match)
        track_data_update = {
            "title": "Unique Title",
            "artist": "Unique Artist",
            "album": "New Album",
        }
        track2 = temp_db.create_or_update_track(track_data_update)

        # Should update the same track
        assert track2.id == track1.id
        assert track2.album == "New Album"

    def test_get_track_by_path_not_found(self, temp_db):
        """Test get_track_by_path returns None when not found."""
        track = temp_db.get_track_by_path("/nonexistent.mp3")
        assert track is None

    def test_find_track_by_metadata_not_found(self, temp_db):
        """Test find_track_by_metadata returns None when not found."""
        track = temp_db.find_track_by_metadata("No Title", "No Artist")
        assert track is None

    def test_find_track_by_normalized_name_not_found(self, temp_db):
        """Test find_track_by_normalized_name returns None when not found."""
        track = temp_db.find_track_by_normalized_name("no artist - no title")
        assert track is None

    def test_find_track_by_normalized_name(self, temp_db):
        """Test find_track_by_normalized_name finds track."""
        # Create track
        track = temp_db.create_track(
            {
                "title": "Test Song",
                "artist": "Test Artist",
            }
        )

        # Find by normalized name
        found = temp_db.find_track_by_normalized_name(track.normalized_name)
        assert found is not None
        assert found.id == track.id

    def test_get_all_tracks(self, temp_db):
        """Test get_all_tracks returns all tracks."""
        # Create multiple tracks
        temp_db.create_track(
            {"tidal_id": "1", "title": "Track 1", "artist": "Artist 1"}
        )
        temp_db.create_track(
            {"tidal_id": "2", "title": "Track 2", "artist": "Artist 2"}
        )
        temp_db.create_track(
            {"tidal_id": "3", "title": "Track 3", "artist": "Artist 3"}
        )

        all_tracks = temp_db.get_all_tracks()
        assert len(all_tracks) == 3

    def test_get_playlist_by_name(self, temp_db):
        """Test get_playlist_by_name finds playlist."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Unique Name"})

        found = temp_db.get_playlist_by_name("Unique Name")
        assert found is not None
        assert found.id == playlist.id

    def test_get_playlist_by_name_not_found(self, temp_db):
        """Test get_playlist_by_name returns None when not found."""
        playlist = temp_db.get_playlist_by_name("Nonexistent Playlist")
        assert playlist is None

    def test_get_all_playlists(self, temp_db):
        """Test get_all_playlists returns all playlists."""
        temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})
        temp_db.create_playlist({"tidal_id": "pl2", "name": "Playlist 2"})

        all_playlists = temp_db.get_all_playlists()
        assert len(all_playlists) == 2

    def test_get_playlist_tracks_empty(self, temp_db):
        """Test get_playlist_tracks returns empty list for nonexistent playlist."""
        tracks = temp_db.get_playlist_tracks(99999)
        assert tracks == []

    def test_get_playlist_track_associations(self, temp_db):
        """Test get_playlist_track_associations returns PlaylistTrack objects."""
        # Create playlist and tracks
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Test"})
        track1 = temp_db.create_track(
            {"tidal_id": "1", "title": "Track 1", "artist": "A1"}
        )
        track2 = temp_db.create_track(
            {"tidal_id": "2", "title": "Track 2", "artist": "A2"}
        )

        temp_db.add_track_to_playlist(playlist.id, track1.id, position=1, in_tidal=True)
        temp_db.add_track_to_playlist(playlist.id, track2.id, position=2, in_tidal=True)

        associations = temp_db.get_playlist_track_associations(playlist.id)
        assert len(associations) == 2
        assert associations[0].position == 1
        assert associations[1].position == 2
        assert associations[0].track.title == "Track 1"

    def test_get_track_playlists(self, temp_db):
        """Test get_track_playlists returns all playlists containing a track."""
        track = temp_db.create_track(
            {"tidal_id": "1", "title": "Track", "artist": "Artist"}
        )
        pl1 = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})
        pl2 = temp_db.create_playlist({"tidal_id": "pl2", "name": "Playlist 2"})

        temp_db.add_track_to_playlist(pl1.id, track.id, position=1, in_tidal=True)
        temp_db.add_track_to_playlist(pl2.id, track.id, position=1, in_tidal=True)

        playlists = temp_db.get_track_playlists(track.id)
        assert len(playlists) == 2

    def test_get_track_playlists_empty(self, temp_db):
        """Test get_track_playlists returns empty list for nonexistent track."""
        playlists = temp_db.get_track_playlists(99999)
        assert playlists == []

    def test_update_track_position(self, temp_db):
        """Test update_track_position updates position."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Test"})
        track = temp_db.create_track(
            {"tidal_id": "1", "title": "Track", "artist": "Artist"}
        )
        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_tidal=True)

        result = temp_db.update_track_position(playlist.id, track.id, 5)
        assert result is True

        # Verify position changed
        associations = temp_db.get_playlist_track_associations(playlist.id)
        assert associations[0].position == 5

    def test_update_track_position_not_found(self, temp_db):
        """Test update_track_position returns False when not found."""
        result = temp_db.update_track_position(99999, 99999, 1)
        assert result is False

    def test_update_track_sync_state(self, temp_db):
        """Test update_track_sync_state updates flags."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Test"})
        track = temp_db.create_track(
            {"tidal_id": "1", "title": "Track", "artist": "Artist"}
        )
        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_tidal=False)

        result = temp_db.update_track_sync_state(
            playlist.id, track.id, in_tidal=True, in_local=True, in_rekordbox=True
        )
        assert result is True

        associations = temp_db.get_playlist_track_associations(playlist.id)
        assert associations[0].in_tidal is True
        assert associations[0].in_local is True
        assert associations[0].in_rekordbox is True

    def test_update_track_sync_state_not_found(self, temp_db):
        """Test update_track_sync_state returns False when not found."""
        result = temp_db.update_track_sync_state(99999, 99999, in_tidal=True)
        assert result is False

    def test_update_operation_status_running(self, temp_db):
        """Test update_operation_status sets started_at when running."""
        operation = temp_db.create_sync_operation(
            {
                "operation_type": "download",
                "status": "pending",
            }
        )

        updated = temp_db.update_operation_status(operation.id, "running")
        assert updated.status == "running"
        assert updated.started_at is not None

    def test_update_operation_status_failed(self, temp_db):
        """Test update_operation_status handles failed status."""
        operation = temp_db.create_sync_operation(
            {
                "operation_type": "download",
                "status": "pending",
            }
        )

        updated = temp_db.update_operation_status(
            operation.id, "failed", error_message="Connection timeout"
        )
        assert updated.status == "failed"
        assert updated.completed_at is not None
        assert updated.error_message == "Connection timeout"

    def test_compute_file_hash(self, temp_db):
        """Test compute_file_hash computes SHA256 hash."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            hash_value = DatabaseService.compute_file_hash(temp_path)
            assert isinstance(hash_value, str)
            assert len(hash_value) == 64  # SHA256 produces 64 hex characters
        finally:
            temp_path.unlink()

    def test_remove_track_from_playlist_local(self, temp_db):
        """Test remove_track_from_playlist with source='local'."""
        track = temp_db.create_track(
            {"tidal_id": "1", "title": "Track", "artist": "Artist"}
        )
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_local=True)

        result = temp_db.remove_track_from_playlist(
            playlist.id, track.id, source="local"
        )
        assert result is True

    def test_remove_track_from_playlist_rekordbox(self, temp_db):
        """Test remove_track_from_playlist with source='rekordbox'."""
        track = temp_db.create_track(
            {"tidal_id": "1", "title": "Track", "artist": "Artist"}
        )
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        temp_db.add_track_to_playlist(
            playlist.id, track.id, position=1, in_rekordbox=True
        )

        result = temp_db.remove_track_from_playlist(
            playlist.id, track.id, source="rekordbox"
        )
        assert result is True

    def test_remove_track_from_playlist_deletes_when_all_false(self, temp_db):
        """Test remove_track_from_playlist deletes when all sources false."""
        track = temp_db.create_track(
            {"tidal_id": "1", "title": "Track", "artist": "Artist"}
        )
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_tidal=True)

        # Remove from tidal (only source)
        result = temp_db.remove_track_from_playlist(
            playlist.id, track.id, source="tidal"
        )
        assert result is True

        # Verify relationship deleted
        tracks = temp_db.get_playlist_tracks(playlist.id)
        assert len(tracks) == 0

    def test_add_track_to_playlist_updates_existing(self, temp_db):
        """Test add_track_to_playlist updates existing relationship."""
        track = temp_db.create_track(
            {"tidal_id": "1", "title": "Track", "artist": "Artist"}
        )
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})

        # Add initially
        pt1 = temp_db.add_track_to_playlist(
            playlist.id, track.id, position=1, in_tidal=True
        )

        # Add again with different flags
        pt2 = temp_db.add_track_to_playlist(
            playlist.id, track.id, position=2, in_local=True, in_rekordbox=True
        )

        # Should be same relationship
        assert pt1.playlist_id == pt2.playlist_id
        assert pt1.track_id == pt2.track_id
        assert pt2.position == 2
        assert pt2.in_tidal is True
        assert pt2.in_local is True
        assert pt2.in_rekordbox is True

    def test_get_tracks_by_download_status(self, temp_db):
        """Test get_tracks_by_download_status filters correctly."""
        temp_db.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "Artist",
                "download_status": "downloaded",
            }
        )
        temp_db.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "Artist",
                "download_status": "not_downloaded",
            }
        )
        temp_db.create_track(
            {
                "tidal_id": "3",
                "title": "Track 3",
                "artist": "Artist",
                "download_status": "downloaded",
            }
        )

        downloaded = temp_db.get_tracks_by_download_status("downloaded")
        assert len(downloaded) == 2

        not_downloaded = temp_db.get_tracks_by_download_status("not_downloaded")
        assert len(not_downloaded) == 1

    def test_get_tracks_by_download_status_with_limit(self, temp_db):
        """Test get_tracks_by_download_status with limit."""
        for i in range(5):
            temp_db.create_track(
                {
                    "tidal_id": str(i),
                    "title": f"Track {i}",
                    "artist": "Artist",
                    "download_status": "downloaded",
                }
            )

        tracks = temp_db.get_tracks_by_download_status("downloaded", limit=3)
        assert len(tracks) == 3

    def test_get_playlists_by_sync_status(self, temp_db):
        """Test get_playlists_by_sync_status filters correctly."""
        temp_db.create_playlist(
            {
                "tidal_id": "pl1",
                "name": "Playlist 1",
                "sync_status": "in_sync",
            }
        )
        temp_db.create_playlist(
            {
                "tidal_id": "pl2",
                "name": "Playlist 2",
                "sync_status": "needs_download",
            }
        )

        in_sync = temp_db.get_playlists_by_sync_status("in_sync")
        assert len(in_sync) == 1

        needs_download = temp_db.get_playlists_by_sync_status("needs_download")
        assert len(needs_download) == 1

    def test_get_playlists_by_sync_status_with_limit(self, temp_db):
        """Test get_playlists_by_sync_status with limit."""
        for i in range(5):
            temp_db.create_playlist(
                {
                    "tidal_id": f"pl{i}",
                    "name": f"Playlist {i}",
                    "sync_status": "in_sync",
                }
            )

        playlists = temp_db.get_playlists_by_sync_status("in_sync", limit=2)
        assert len(playlists) == 2

    def test_update_track_download_status(self, temp_db):
        """Test update_track_download_status updates status."""
        track = temp_db.create_track(
            {
                "tidal_id": "1",
                "title": "Track",
                "artist": "Artist",
                "download_status": "not_downloaded",
            }
        )

        updated = temp_db.update_track_download_status(track.id, "downloaded")
        assert updated.download_status == "downloaded"
        assert updated.downloaded_at is not None

    def test_update_track_download_status_with_error(self, temp_db):
        """Test update_track_download_status handles error."""
        track = temp_db.create_track(
            {
                "tidal_id": "1",
                "title": "Track",
                "artist": "Artist",
            }
        )

        updated = temp_db.update_track_download_status(
            track.id, "error", error="Network timeout"
        )
        assert updated.download_status == "error"
        assert updated.download_error == "Network timeout"

    def test_update_playlist_sync_status(self, temp_db):
        """Test update_playlist_sync_status updates status."""
        playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl1",
                "name": "Playlist",
                "sync_status": "needs_download",
            }
        )

        updated = temp_db.update_playlist_sync_status(playlist.id, "in_sync")
        assert updated.sync_status == "in_sync"
        assert updated.last_synced_filesystem is not None

    def test_set_track_rekordbox_id(self, temp_db):
        """Test storing Rekordbox content identifiers on tracks."""
        track = temp_db.create_track(
            {
                "tidal_id": "t1",
                "title": "Track",
                "artist": "Artist",
            }
        )

        updated = temp_db.set_track_rekordbox_id(track.id, "CONTENT-9")
        assert updated is True

        refreshed = temp_db.get_track_by_id(track.id)
        assert refreshed is not None
        assert refreshed.rekordbox_content_id == "CONTENT-9"

    def test_get_tracks_needing_download(self, temp_db):
        """Test get_tracks_needing_download returns not_downloaded tracks."""
        temp_db.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "Artist",
                "download_status": "not_downloaded",
            }
        )
        temp_db.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "Artist",
                "download_status": "downloaded",
            }
        )

        tracks = temp_db.get_tracks_needing_download()
        assert len(tracks) == 1
        assert tracks[0].download_status == "not_downloaded"

    def test_get_tracks_with_errors(self, temp_db):
        """Test get_tracks_with_errors returns error tracks."""
        temp_db.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "Artist",
                "download_status": "error",
            }
        )
        temp_db.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "Artist",
                "download_status": "downloaded",
            }
        )

        tracks = temp_db.get_tracks_with_errors()
        assert len(tracks) == 1
        assert tracks[0].download_status == "error"

    def test_get_playlists_needing_sync(self, temp_db):
        """Test get_playlists_needing_sync returns playlists needing sync."""
        temp_db.create_playlist(
            {
                "tidal_id": "pl1",
                "name": "Playlist 1",
                "sync_status": "needs_download",
            }
        )
        temp_db.create_playlist(
            {
                "tidal_id": "pl2",
                "name": "Playlist 2",
                "sync_status": "needs_update",
            }
        )
        temp_db.create_playlist(
            {
                "tidal_id": "pl3",
                "name": "Playlist 3",
                "sync_status": "in_sync",
            }
        )

        playlists = temp_db.get_playlists_needing_sync()
        assert len(playlists) == 2

    def test_get_primary_playlist_tracks(self, temp_db):
        """Test get_primary_playlist_tracks returns primary tracks."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        track1 = temp_db.create_track(
            {"tidal_id": "1", "title": "Track 1", "artist": "A"}
        )
        track2 = temp_db.create_track(
            {"tidal_id": "2", "title": "Track 2", "artist": "A"}
        )

        temp_db.add_track_to_playlist(playlist.id, track1.id, position=1, in_tidal=True)
        temp_db.add_track_to_playlist(playlist.id, track2.id, position=2, in_tidal=True)

        # Mark first as primary
        temp_db.mark_playlist_track_as_primary(playlist.id, track1.id)

        primary = temp_db.get_primary_playlist_tracks(playlist.id)
        assert len(primary) == 1
        assert primary[0].track_id == track1.id

    def test_get_symlink_playlist_tracks(self, temp_db):
        """Test get_symlink_playlist_tracks returns non-primary tracks."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        track1 = temp_db.create_track(
            {"tidal_id": "1", "title": "Track 1", "artist": "A"}
        )
        track2 = temp_db.create_track(
            {"tidal_id": "2", "title": "Track 2", "artist": "A"}
        )

        temp_db.add_track_to_playlist(playlist.id, track1.id, position=1, in_tidal=True)
        temp_db.add_track_to_playlist(playlist.id, track2.id, position=2, in_tidal=True)

        # Mark first as primary (second remains non-primary)
        temp_db.mark_playlist_track_as_primary(playlist.id, track1.id)

        symlinks = temp_db.get_symlink_playlist_tracks(playlist.id)
        assert len(symlinks) == 1
        assert symlinks[0].track_id == track2.id

    def test_get_broken_symlinks(self, temp_db):
        """Test get_broken_symlinks returns invalid symlinks."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        track = temp_db.create_track({"tidal_id": "1", "title": "Track", "artist": "A"})

        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_tidal=True)
        temp_db.update_symlink_status(playlist.id, track.id, "/path/broken", False)

        broken = temp_db.get_broken_symlinks()
        assert len(broken) == 1
        assert broken[0].symlink_valid is False

    def test_get_duplicate_tracks(self, temp_db):
        """Test get_duplicate_tracks returns tracks in multiple playlists."""
        pl1 = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})
        pl2 = temp_db.create_playlist({"tidal_id": "pl2", "name": "Playlist 2"})
        track1 = temp_db.create_track(
            {"tidal_id": "1", "title": "Track 1", "artist": "A"}
        )
        track2 = temp_db.create_track(
            {"tidal_id": "2", "title": "Track 2", "artist": "A"}
        )

        # track1 in both playlists
        temp_db.add_track_to_playlist(pl1.id, track1.id, position=1, in_tidal=True)
        temp_db.add_track_to_playlist(pl2.id, track1.id, position=1, in_tidal=True)

        # track2 in only one playlist
        temp_db.add_track_to_playlist(pl1.id, track2.id, position=2, in_tidal=True)

        duplicates = temp_db.get_duplicate_tracks()
        assert track1.id in duplicates
        assert len(duplicates[track1.id]) == 2
        assert track2.id not in duplicates

    def test_mark_playlist_track_as_primary(self, temp_db):
        """Test mark_playlist_track_as_primary marks track as primary."""
        pl1 = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist 1"})
        pl2 = temp_db.create_playlist({"tidal_id": "pl2", "name": "Playlist 2"})
        track = temp_db.create_track({"tidal_id": "1", "title": "Track", "artist": "A"})

        temp_db.add_track_to_playlist(pl1.id, track.id, position=1, in_tidal=True)
        temp_db.add_track_to_playlist(pl2.id, track.id, position=1, in_tidal=True)

        # Mark as primary in pl1
        pt = temp_db.mark_playlist_track_as_primary(pl1.id, track.id)
        assert pt is not None
        assert pt.is_primary is True
        assert pt.sync_status == "synced"
        assert pt.synced_at is not None

        # Verify pl2 is not primary
        pl2_tracks = temp_db.get_playlist_track_associations(pl2.id)
        assert pl2_tracks[0].is_primary is False

    def test_mark_playlist_track_as_primary_not_found(self, temp_db):
        """Test mark_playlist_track_as_primary returns None when not found."""
        pt = temp_db.mark_playlist_track_as_primary(99999, 99999)
        assert pt is None

    def test_update_symlink_status(self, temp_db):
        """Test update_symlink_status updates symlink information."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        track = temp_db.create_track({"tidal_id": "1", "title": "Track", "artist": "A"})

        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_tidal=True)

        pt = temp_db.update_symlink_status(playlist.id, track.id, "/path/symlink", True)
        assert pt is not None
        assert pt.symlink_path == "/path/symlink"
        assert pt.symlink_valid is True
        assert pt.is_primary is False
        assert pt.sync_status == "synced"

    def test_update_symlink_status_invalid(self, temp_db):
        """Test update_symlink_status with invalid symlink."""
        playlist = temp_db.create_playlist({"tidal_id": "pl1", "name": "Playlist"})
        track = temp_db.create_track({"tidal_id": "1", "title": "Track", "artist": "A"})

        temp_db.add_track_to_playlist(playlist.id, track.id, position=1, in_tidal=True)

        pt = temp_db.update_symlink_status(playlist.id, track.id, "/broken", False)
        assert pt is not None
        assert pt.symlink_valid is False
        assert pt.sync_status == "needs_symlink"
        assert pt.synced_at is None

    def test_update_symlink_status_not_found(self, temp_db):
        """Test update_symlink_status returns None when not found."""
        pt = temp_db.update_symlink_status(99999, 99999, "/path", True)
        assert pt is None

    def test_get_sync_statistics(self, temp_db):
        """Test get_sync_statistics returns comprehensive stats."""
        # Create tracks with different statuses
        temp_db.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "A",
                "download_status": "downloaded",
            }
        )
        temp_db.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "A",
                "download_status": "not_downloaded",
            }
        )
        temp_db.create_track(
            {
                "tidal_id": "3",
                "title": "Track 3",
                "artist": "A",
                "download_status": "error",
            }
        )

        # Create playlists with different statuses
        temp_db.create_playlist(
            {
                "tidal_id": "pl1",
                "name": "Playlist 1",
                "sync_status": "in_sync",
            }
        )
        temp_db.create_playlist(
            {
                "tidal_id": "pl2",
                "name": "Playlist 2",
                "sync_status": "needs_download",
            }
        )

        stats = temp_db.get_sync_statistics()

        # Verify track stats
        assert stats["tracks"]["total"] == 3
        assert stats["tracks"]["downloaded"] == 1
        assert stats["tracks"]["not_downloaded"] == 1
        assert stats["tracks"]["errors"] == 1

        # Verify playlist stats
        assert stats["playlists"]["total"] == 2
        assert stats["playlists"]["in_sync"] == 1
        assert stats["playlists"]["needs_download"] == 1

        # Verify structure
        assert "deduplication" in stats
        assert "database_path" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
