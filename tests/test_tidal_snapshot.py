"""Tests for Tidal Snapshot Service."""

from unittest.mock import Mock

import pytest

from tidal_cleanup.core.sync.state import ChangeType
from tidal_cleanup.core.tidal.snapshot_service import TidalSnapshotService
from tidal_cleanup.database import DatabaseService
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
        from tidal_cleanup.core.sync.state import Change, SyncState

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

        changes = tidal_snapshot_service._filter_playlist_changes(sync_state)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.PLAYLIST_ADDED

    def test_get_track_changes(self, tidal_snapshot_service):
        """Test filtering track changes."""
        from tidal_cleanup.core.sync.state import Change, SyncState

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

        changes = tidal_snapshot_service._filter_track_changes(sync_state)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.TRACK_ADDED_TO_PLAYLIST


class TestTidalSnapshotEdgeCases:
    """Test edge cases and error handling."""

    def test_capture_snapshot_playlist_without_tidal_id(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test capturing snapshot when playlist has no tidal_id."""
        # Mock playlist without tidal_id
        mock_playlist = Mock()
        mock_playlist.name = "Invalid Playlist"
        mock_playlist.tidal_id = None
        mock_playlist.description = "Test"

        mock_tidal_service.get_playlists.return_value = [mock_playlist]

        # Should not crash
        sync_state = tidal_snapshot_service.capture_tidal_snapshot()

        # Should complete without processing the invalid playlist
        assert sync_state is not None
        assert sync_state.tidal_playlists_count == 1

    def test_apply_playlist_changes_with_error(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test error handling in apply_playlist_changes."""
        from tidal_cleanup.core.sync.state import Change, SyncState

        # Create a change that will cause an error
        sync_state = SyncState()
        change = Change(
            change_type=ChangeType.PLAYLIST_ADDED,
            entity_type="playlist",
            metadata={},  # Missing tidal_id will cause error
        )
        sync_state.add_change(change)

        # Mock to return empty playlists
        mock_tidal_service.get_playlists.return_value = []

        # Should not crash, should log error and continue
        result = tidal_snapshot_service.apply_tidal_state_to_db(sync_state)

        # Should return empty counts since change failed
        assert isinstance(result, dict)

    def test_apply_track_changes_with_error(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test error handling in apply_track_changes."""
        from tidal_cleanup.core.sync.state import Change, SyncState

        # Create a change that will cause an error
        sync_state = SyncState()
        change = Change(
            change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
            entity_type="track",
            metadata={},  # Missing required data
        )
        sync_state.add_change(change)

        # Should not crash, should log error and continue
        result = tidal_snapshot_service.apply_tidal_state_to_db(sync_state)

        # Should return empty counts since change failed
        assert isinstance(result, dict)

    def test_apply_playlist_removed(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying PLAYLIST_REMOVED change (soft delete)."""
        from tidal_cleanup.core.sync.state import Change

        # Create playlist with tracks in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )
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

        # Create removal change
        change = Change(
            change_type=ChangeType.PLAYLIST_REMOVED,
            entity_type="playlist",
            entity_id=db_playlist.id,
            old_value="Test Playlist",
        )

        # Apply change
        tidal_snapshot_service._handle_playlist_removed(change)

        # Verify tracks marked as not in Tidal
        playlist_tracks = temp_db.get_playlist_track_associations(db_playlist.id)
        assert len(playlist_tracks) == 1
        assert playlist_tracks[0].in_tidal is False

    def test_apply_playlist_removed_without_entity_id(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test apply_playlist_removed without entity_id."""
        from tidal_cleanup.core.sync.state import Change

        # Create change without entity_id
        change = Change(
            change_type=ChangeType.PLAYLIST_REMOVED,
            entity_type="playlist",
            entity_id=None,
            old_value="Test",
        )

        # Should log warning and return without error
        tidal_snapshot_service._handle_playlist_removed(change)

    def test_apply_playlist_renamed(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying PLAYLIST_RENAMED change."""
        from tidal_cleanup.core.sync.state import Change

        # Create playlist in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Old Name",
                "description": "Test",
            }
        )

        # Create rename change
        change = Change(
            change_type=ChangeType.PLAYLIST_RENAMED,
            entity_type="playlist",
            entity_id=db_playlist.id,
            old_value="Old Name",
            new_value="New Name",
        )

        # Apply change
        tidal_snapshot_service._handle_playlist_renamed(change)

        # Verify playlist was renamed
        updated = temp_db.get_playlist_by_id(db_playlist.id)
        assert updated.name == "New Name"

    def test_apply_playlist_renamed_missing_data(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test apply_playlist_renamed with missing data."""
        from tidal_cleanup.core.sync.state import Change

        # Create change without new_value
        change = Change(
            change_type=ChangeType.PLAYLIST_RENAMED,
            entity_type="playlist",
            entity_id=1,
            old_value="Old Name",
            new_value=None,
        )

        # Should log warning and return without error
        tidal_snapshot_service._handle_playlist_renamed(change)

    def test_apply_playlist_description_changed(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying PLAYLIST_DESCRIPTION_CHANGED change."""
        from tidal_cleanup.core.sync.state import Change

        # Create playlist in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Old Description",
            }
        )

        # Create description change
        change = Change(
            change_type=ChangeType.PLAYLIST_DESCRIPTION_CHANGED,
            entity_type="playlist",
            entity_id=db_playlist.id,
            old_value="Old Description",
            new_value="New Description",
        )

        # Apply change
        tidal_snapshot_service._handle_playlist_description_changed(change)

        # Verify description was updated
        updated = temp_db.get_playlist_by_id(db_playlist.id)
        assert updated.description == "New Description"

    def test_apply_playlist_description_changed_without_entity_id(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test apply_playlist_description_changed without entity_id."""
        from tidal_cleanup.core.sync.state import Change

        # Create change without entity_id
        change = Change(
            change_type=ChangeType.PLAYLIST_DESCRIPTION_CHANGED,
            entity_type="playlist",
            entity_id=None,
            new_value="Test",
        )

        # Should log warning and return without error
        tidal_snapshot_service._handle_playlist_description_changed(change)

    def test_apply_track_removed_from_playlist(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying TRACK_REMOVED_FROM_PLAYLIST change (soft delete)."""
        from tidal_cleanup.core.sync.state import Change

        # Create playlist and track in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )
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

        # Create removal change
        change = Change(
            change_type=ChangeType.TRACK_REMOVED_FROM_PLAYLIST,
            entity_type="track",
            playlist_id=db_playlist.id,
            track_id=db_track.id,
        )

        # Apply change
        tidal_snapshot_service._handle_track_removed(change)

        # Verify track marked as not in Tidal
        playlist_tracks = temp_db.get_playlist_track_associations(db_playlist.id)
        assert len(playlist_tracks) == 1
        assert playlist_tracks[0].in_tidal is False

    def test_apply_track_removed_missing_data(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test apply_track_removed_from_playlist with missing data."""
        from tidal_cleanup.core.sync.state import Change

        # Create change without required data
        change = Change(
            change_type=ChangeType.TRACK_REMOVED_FROM_PLAYLIST,
            entity_type="track",
            playlist_id=None,
            track_id=None,
        )

        # Should log warning and return without error
        tidal_snapshot_service._handle_track_removed(change)

    def test_apply_track_moved_within_playlist(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying TRACK_MOVED_WITHIN_PLAYLIST change."""
        from tidal_cleanup.core.sync.state import Change

        # Create playlist and track in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )
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

        # Create move change
        change = Change(
            change_type=ChangeType.TRACK_MOVED_WITHIN_PLAYLIST,
            entity_type="track",
            playlist_id=db_playlist.id,
            track_id=db_track.id,
            old_value="0",
            new_value="2",
        )

        # Apply change
        tidal_snapshot_service._handle_track_moved(change)

        # Verify position was updated
        playlist_tracks = temp_db.get_playlist_track_associations(db_playlist.id)
        assert len(playlist_tracks) == 1
        assert playlist_tracks[0].position == 2

    def test_apply_track_moved_missing_data(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test apply_track_moved_within_playlist with missing data."""
        from tidal_cleanup.core.sync.state import Change

        # Create change without new_value
        change = Change(
            change_type=ChangeType.TRACK_MOVED_WITHIN_PLAYLIST,
            entity_type="track",
            playlist_id=1,
            track_id=1,
            new_value=None,
        )

        # Should log warning and return without error
        tidal_snapshot_service._handle_track_moved(change)

    def test_apply_track_metadata_changed(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test applying TRACK_METADATA_CHANGED change."""
        from tidal_cleanup.core.sync.state import Change

        # Create track in database
        db_track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Old Title",
                "artist": "Old Artist",
                "album": "Old Album",
            }
        )

        # Create metadata change
        change = Change(
            change_type=ChangeType.TRACK_METADATA_CHANGED,
            entity_type="track",
            track_id=db_track.id,
            metadata={
                "changes": {
                    "title": {"old": "Old Title", "new": "New Title"},
                    "artist": {"old": "Old Artist", "new": "New Artist"},
                }
            },
        )

        # Apply change
        tidal_snapshot_service._handle_track_metadata_changed(change)

        # Verify metadata was updated
        updated = temp_db.get_track_by_id(db_track.id)
        assert updated.title == "New Title"
        assert updated.artist == "New Artist"

    def test_apply_track_metadata_changed_missing_data(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test apply_track_metadata_changed with missing data."""
        from tidal_cleanup.core.sync.state import Change

        # Create change without changes
        change = Change(
            change_type=ChangeType.TRACK_METADATA_CHANGED,
            entity_type="track",
            track_id=None,
            metadata={},
        )

        # Should log warning and return without error
        tidal_snapshot_service._handle_track_metadata_changed(change)

    def test_apply_track_added_to_playlist_with_existing_track(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test adding track that already exists in database."""
        from tidal_cleanup.core.sync.state import Change

        # Create playlist and track in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )
        temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
                "album": "Album 1",
            }
        )

        # Create track addition change
        change = Change(
            change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
            entity_type="track",
            playlist_id=db_playlist.id,
            metadata={"tidal_id": "tr123", "position": 0},
        )

        # Apply change
        tidal_snapshot_service._handle_track_added(change)

        # Verify track was added to playlist
        playlist_tracks = temp_db.get_playlist_tracks(db_playlist.id)
        assert len(playlist_tracks) == 1
        assert playlist_tracks[0].tidal_id == "tr123"

    def test_apply_track_added_to_playlist_new_track(
        self, tidal_snapshot_service, mock_tidal_service, temp_db
    ):
        """Test adding new track from Tidal."""
        from tidal_cleanup.core.sync.state import Change

        # Create playlist in database
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )

        # Mock Tidal API to return track
        mock_track = TidalTrack(
            title="New Track",
            artist="New Artist",
            album="New Album",
            tidal_id="tr456",
            duration=180,
        )
        mock_tidal_service.get_playlist_tracks.return_value = [mock_track]

        # Create track addition change
        change = Change(
            change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
            entity_type="track",
            playlist_id=db_playlist.id,
            metadata={"tidal_id": "tr456", "position": 0},
        )

        # Apply change
        tidal_snapshot_service._handle_track_added(change)

        # Verify track was created and added to playlist
        playlist_tracks = temp_db.get_playlist_tracks(db_playlist.id)
        assert len(playlist_tracks) == 1
        assert playlist_tracks[0].tidal_id == "tr456"
        assert playlist_tracks[0].title == "New Track"

    def test_apply_track_added_missing_data(
        self, tidal_snapshot_service, mock_tidal_service
    ):
        """Test apply_track_added_to_playlist with missing data."""
        from tidal_cleanup.core.sync.state import Change

        # Create change without required data
        change = Change(
            change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
            entity_type="track",
            playlist_id=None,
            metadata={},
        )

        # Should log warning and return without error
        tidal_snapshot_service._handle_track_added(change)
