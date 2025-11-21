"""Tests for Tidal Snapshot Service."""

from unittest.mock import Mock

import pytest

from tidal_cleanup.database import (
    DatabaseService,
    TidalSnapshotService,
)
from tidal_cleanup.database.sync_state import ChangeType
from tidal_cleanup.models.models import Playlist as TidalPlaylist
from tidal_cleanup.models.models import Track as TidalTrack


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = DatabaseService(str(db_path))
    db.init_db()
    return db


@pytest.fixture
def mock_tidal_service():
    """Create a mock Tidal service."""
    service = Mock()
    service.is_authenticated.return_value = True
    return service


@pytest.fixture
def tidal_snapshot_service(mock_tidal_service, temp_db):
    """Create Tidal snapshot service with mocks."""
    return TidalSnapshotService(mock_tidal_service, temp_db)


class TestTidalSnapshotServiceInit:
    """Test TidalSnapshotService initialization."""

    def test_init(self, mock_tidal_service, temp_db):
        """Test service initialization."""
        service = TidalSnapshotService(mock_tidal_service, temp_db)

        assert service.tidal_service == mock_tidal_service
        assert service.db_service == temp_db
        assert service.comparator is not None


class TestCaptureSnapshot:
    """Test capturing Tidal snapshot."""

    def test_capture_snapshot_empty_database(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test capturing snapshot when database is empty."""
        # Mock Tidal API responses
        mock_playlist = TidalPlaylist(
            name="Test Playlist", tidal_id="pl123", description="Test description"
        )
        mock_tidal_service.get_playlists.return_value = [mock_playlist]
        mock_tidal_service.get_playlist_tracks.return_value = []

        # Capture snapshot
        sync_state = tidal_snapshot_service.capture_tidal_snapshot()

        # Verify state
        assert sync_state.tidal_playlists_count == 1
        assert sync_state.database_playlists_count == 0
        assert sync_state.has_changes() is True

        # Should detect playlist added
        playlist_added_changes = sync_state.get_changes_by_type(
            ChangeType.PLAYLIST_ADDED
        )
        assert len(playlist_added_changes) == 1
        assert playlist_added_changes[0].new_value == "Test Playlist"

    def test_capture_snapshot_with_tracks(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test capturing snapshot with tracks."""
        # Create playlist in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )

        # Create track in database
        db_track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
                "album": "Album 1",
            }
        )
        temp_db.add_track_to_playlist(
            db_playlist.id, db_track.id, position=0, in_tidal=True
        )

        # Mock Tidal API responses
        mock_playlist = TidalPlaylist(
            name="Test Playlist", tidal_id="pl123", description="Test"
        )
        mock_track1 = TidalTrack(
            title="Track 1",
            artist="Artist 1",
            album="Album 1",
            tidal_id="tr123",
            duration=180,
        )
        mock_track2 = TidalTrack(
            title="Track 2",
            artist="Artist 2",
            album="Album 2",
            tidal_id="tr456",
            duration=200,
        )

        mock_tidal_service.get_playlists.return_value = [mock_playlist]
        mock_tidal_service.get_playlist_tracks.return_value = [
            mock_track1,
            mock_track2,
        ]

        # Capture snapshot
        sync_state = tidal_snapshot_service.capture_tidal_snapshot()

        # Verify state
        assert sync_state.tidal_playlists_count == 1
        assert sync_state.database_playlists_count == 1

        # Should detect one new track
        track_added_changes = sync_state.get_changes_by_type(
            ChangeType.TRACK_ADDED_TO_PLAYLIST
        )
        assert len(track_added_changes) == 1

    def test_capture_snapshot_detect_removed_playlist(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test detecting removed playlist."""
        # Create playlist in database
        temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Old Playlist",
                "description": "Will be removed",
            }
        )

        # Mock Tidal returns no playlists
        mock_tidal_service.get_playlists.return_value = []

        # Capture snapshot
        sync_state = tidal_snapshot_service.capture_tidal_snapshot()

        # Should detect playlist removal
        playlist_removed = sync_state.get_changes_by_type(ChangeType.PLAYLIST_REMOVED)
        assert len(playlist_removed) == 1
        assert playlist_removed[0].old_value == "Old Playlist"

    def test_capture_snapshot_detect_renamed_playlist(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test detecting renamed playlist."""
        # Create playlist in database
        temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Old Name",
                "description": "Test",
            }
        )

        # Mock Tidal returns playlist with new name
        mock_playlist = TidalPlaylist(
            name="New Name", tidal_id="pl123", description="Test"
        )
        mock_tidal_service.get_playlists.return_value = [mock_playlist]
        mock_tidal_service.get_playlist_tracks.return_value = []

        # Capture snapshot
        sync_state = tidal_snapshot_service.capture_tidal_snapshot()

        # Should detect rename
        renamed = sync_state.get_changes_by_type(ChangeType.PLAYLIST_RENAMED)
        assert len(renamed) == 1
        assert renamed[0].old_value == "Old Name"
        assert renamed[0].new_value == "New Name"


class TestApplyChanges:
    """Test applying changes to database."""

    def test_apply_playlist_added(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying PLAYLIST_ADDED change."""
        # Mock Tidal API
        mock_playlist = TidalPlaylist(
            name="New Playlist", tidal_id="pl123", description="New"
        )
        mock_tidal_service.get_playlists.return_value = [mock_playlist]
        mock_tidal_service.get_playlist_tracks.return_value = []

        # Capture and apply
        sync_state = tidal_snapshot_service.capture_tidal_snapshot()
        result = tidal_snapshot_service.apply_tidal_state_to_db(sync_state)

        # Verify
        assert result.get("playlist_added", 0) == 1

        # Check database
        db_playlist = temp_db.get_playlist_by_tidal_id("pl123")
        assert db_playlist is not None
        assert db_playlist.name == "New Playlist"

    def test_apply_track_added_to_playlist(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying TRACK_ADDED_TO_PLAYLIST change."""
        # Create playlist in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )

        # Mock Tidal API
        mock_playlist = TidalPlaylist(
            name="Test Playlist", tidal_id="pl123", description="Test"
        )
        mock_track = TidalTrack(
            title="New Track",
            artist="Artist",
            album="Album",
            tidal_id="tr123",
            duration=180,
        )
        mock_tidal_service.get_playlists.return_value = [mock_playlist]
        mock_tidal_service.get_playlist_tracks.return_value = [mock_track]

        # Capture and apply
        sync_state = tidal_snapshot_service.capture_tidal_snapshot()
        result = tidal_snapshot_service.apply_tidal_state_to_db(sync_state)

        # Verify
        assert result.get("track_added_to_playlist", 0) == 1

        # Check database
        db_tracks = temp_db.get_playlist_tracks(db_playlist.id)
        assert len(db_tracks) == 1
        assert db_tracks[0].title == "New Track"

    def test_sync_tidal_to_db(self, tidal_snapshot_service, mock_tidal_service):
        """Test full sync operation."""
        # Mock Tidal API
        mock_playlist = TidalPlaylist(
            name="Test Playlist", tidal_id="pl123", description="Test"
        )
        mock_track = TidalTrack(
            title="Track",
            artist="Artist",
            album="Album",
            tidal_id="tr123",
            duration=180,
        )
        mock_tidal_service.get_playlists.return_value = [mock_playlist]
        mock_tidal_service.get_playlist_tracks.return_value = [mock_track]

        # Perform sync
        result = tidal_snapshot_service.sync_tidal_to_db()

        # Verify result structure
        assert "changes_detected" in result
        assert "changes_applied" in result
        assert "sync_state" in result
        assert result["changes_detected"] > 0


class TestHelperMethods:
    """Test helper methods."""

    def test_get_playlist_changes(self, tidal_snapshot_service):
        """Test filtering playlist changes."""
        from tidal_cleanup.database.sync_state import Change, SyncState

        sync_state = SyncState()
        sync_state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
            )
        )
        sync_state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
            )
        )

        changes = tidal_snapshot_service._get_playlist_changes(sync_state)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.PLAYLIST_ADDED

    def test_get_track_changes(self, tidal_snapshot_service):
        """Test filtering track changes."""
        from tidal_cleanup.database.sync_state import Change, SyncState

        sync_state = SyncState()
        sync_state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
            )
        )
        sync_state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
            )
        )

        changes = tidal_snapshot_service._get_track_changes(sync_state)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.TRACK_ADDED_TO_PLAYLIST
