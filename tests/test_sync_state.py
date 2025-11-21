"""Tests for sync state tracking system."""

from datetime import datetime

import pytest

from tidal_cleanup.database import (
    Change,
    ChangeType,
    DatabaseService,
    SyncState,
    SyncStateComparator,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = DatabaseService(str(db_path))
    db.init_db()
    return db


class TestChange:
    """Test Change class."""

    def test_change_creation(self):
        """Test creating a change."""
        change = Change(
            change_type=ChangeType.PLAYLIST_ADDED,
            entity_type="playlist",
            new_value="New Playlist",
            metadata={"tidal_id": "123"},
        )

        assert change.change_type == ChangeType.PLAYLIST_ADDED
        assert change.entity_type == "playlist"
        assert change.new_value == "New Playlist"
        assert change.metadata["tidal_id"] == "123"
        assert isinstance(change.detected_at, datetime)

    def test_change_string_representation(self):
        """Test change string representation."""
        change = Change(
            change_type=ChangeType.PLAYLIST_RENAMED,
            entity_type="playlist",
            entity_id=1,
            old_value="Old Name",
            new_value="New Name",
        )

        str_repr = str(change)
        assert "[playlist_renamed]" in str_repr
        assert "playlist" in str_repr
        assert "ID: 1" in str_repr
        assert "Old Name → New Name" in str_repr

    def test_change_to_dict(self):
        """Test converting change to dictionary."""
        change = Change(
            change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
            entity_type="track",
            playlist_id=1,
            track_id=2,
            new_value="Artist - Title",
        )

        data = change.to_dict()
        assert data["change_type"] == "track_added_to_playlist"
        assert data["entity_type"] == "track"
        assert data["playlist_id"] == 1
        assert data["track_id"] == 2
        assert data["new_value"] == "Artist - Title"
        assert "detected_at" in data


class TestSyncState:
    """Test SyncState class."""

    def test_sync_state_creation(self):
        """Test creating a sync state."""
        state = SyncState(
            tidal_playlists_count=5,
            tidal_tracks_count=100,
            database_playlists_count=4,
            database_tracks_count=95,
        )

        assert state.tidal_playlists_count == 5
        assert state.tidal_tracks_count == 100
        assert state.database_playlists_count == 4
        assert state.database_tracks_count == 95
        assert len(state.changes) == 0

    def test_add_change(self):
        """Test adding changes to sync state."""
        state = SyncState()
        change1 = Change(
            change_type=ChangeType.PLAYLIST_ADDED,
            entity_type="playlist",
            new_value="Playlist 1",
        )
        change2 = Change(
            change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
            entity_type="track",
            new_value="Track 1",
        )

        state.add_change(change1)
        state.add_change(change2)

        assert len(state.changes) == 2
        assert state.has_changes() is True

    def test_get_changes_by_type(self):
        """Test getting changes by type."""
        state = SyncState()
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
            )
        )

        playlist_added = state.get_changes_by_type(ChangeType.PLAYLIST_ADDED)
        assert len(playlist_added) == 2

        track_added = state.get_changes_by_type(ChangeType.TRACK_ADDED_TO_PLAYLIST)
        assert len(track_added) == 1

    def test_get_changes_by_entity(self):
        """Test getting changes by entity type."""
        state = SyncState()
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
                entity_id=1,
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_RENAMED,
                entity_type="playlist",
                entity_id=1,
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
                entity_id=2,
            )
        )

        playlist_changes = state.get_changes_by_entity("playlist")
        assert len(playlist_changes) == 2

        specific_playlist = state.get_changes_by_entity("playlist", 1)
        assert len(specific_playlist) == 2

        track_changes = state.get_changes_by_entity("track")
        assert len(track_changes) == 1

    def test_get_playlist_changes(self):
        """Test getting changes related to playlists."""
        state = SyncState()
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
                entity_id=1,
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
                playlist_id=1,
                track_id=2,
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
                entity_id=3,
            )
        )

        all_playlist_changes = state.get_playlist_changes()
        assert len(all_playlist_changes) == 3

        specific_playlist = state.get_playlist_changes(playlist_id=1)
        assert len(specific_playlist) == 2

    def test_get_track_changes(self):
        """Test getting changes related to tracks."""
        state = SyncState()
        state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
                track_id=1,
                playlist_id=5,
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.TRACK_METADATA_CHANGED,
                entity_type="track",
                entity_id=1,
                track_id=1,
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
                track_id=2,
                playlist_id=5,
            )
        )

        all_track_changes = state.get_track_changes()
        assert len(all_track_changes) == 3

        specific_track = state.get_track_changes(track_id=1)
        assert len(specific_track) == 2

    def test_get_summary(self):
        """Test getting change summary."""
        state = SyncState()
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
            )
        )
        state.add_change(
            Change(
                change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                entity_type="track",
            )
        )

        summary = state.get_summary()
        assert summary["playlist_added"] == 2
        assert summary["track_added_to_playlist"] == 1

    def test_to_dict(self):
        """Test converting sync state to dictionary."""
        state = SyncState(
            tidal_playlists_count=5,
            tidal_tracks_count=100,
        )
        state.add_change(
            Change(
                change_type=ChangeType.PLAYLIST_ADDED,
                entity_type="playlist",
            )
        )

        data = state.to_dict()
        assert data["counts"]["tidal_playlists"] == 5
        assert data["counts"]["tidal_tracks"] == 100
        assert len(data["changes"]) == 1
        assert data["summary"]["playlist_added"] == 1
        assert "last_sync_times" in data


class TestSyncStateComparator:
    """Test SyncStateComparator class."""

    def test_compare_playlists_new_playlist(self):
        """Test detecting new playlists."""
        comparator = SyncStateComparator()

        db_playlists = []
        snapshot_playlists = [
            {"tidal_id": "123", "name": "New Playlist", "description": "Test"},
        ]

        changes = comparator.compare_playlists(db_playlists, snapshot_playlists)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.PLAYLIST_ADDED
        assert changes[0].new_value == "New Playlist"
        assert changes[0].metadata["tidal_id"] == "123"

    def test_compare_playlists_removed_playlist(self, temp_db):
        """Test detecting removed playlists."""
        comparator = SyncStateComparator()

        # Create playlist in database
        playlist = temp_db.create_playlist({"tidal_id": "123", "name": "Old Playlist"})

        db_playlists = [playlist]
        snapshot_playlists = []

        changes = comparator.compare_playlists(db_playlists, snapshot_playlists)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.PLAYLIST_REMOVED
        assert changes[0].old_value == "Old Playlist"
        assert changes[0].entity_id == playlist.id

    def test_compare_playlists_renamed(self, temp_db):
        """Test detecting playlist renames."""
        comparator = SyncStateComparator()

        # Create playlist in database
        playlist = temp_db.create_playlist({"tidal_id": "123", "name": "Old Name"})

        db_playlists = [playlist]
        snapshot_playlists = [
            {"tidal_id": "123", "name": "New Name", "description": None},
        ]

        changes = comparator.compare_playlists(db_playlists, snapshot_playlists)

        rename_changes = [
            c for c in changes if c.change_type == ChangeType.PLAYLIST_RENAMED
        ]
        assert len(rename_changes) == 1
        assert rename_changes[0].old_value == "Old Name"
        assert rename_changes[0].new_value == "New Name"

    def test_compare_playlists_description_changed(self, temp_db):
        """Test detecting playlist description changes."""
        comparator = SyncStateComparator()

        # Create playlist in database
        playlist = temp_db.create_playlist(
            {
                "tidal_id": "123",
                "name": "Playlist",
                "description": "Old description",
            }
        )

        db_playlists = [playlist]
        snapshot_playlists = [
            {
                "tidal_id": "123",
                "name": "Playlist",
                "description": "New description",
            },
        ]

        changes = comparator.compare_playlists(db_playlists, snapshot_playlists)

        desc_changes = [
            c
            for c in changes
            if c.change_type == ChangeType.PLAYLIST_DESCRIPTION_CHANGED
        ]
        assert len(desc_changes) == 1
        assert desc_changes[0].old_value == "Old description"
        assert desc_changes[0].new_value == "New description"

    def test_compare_playlist_tracks_new_track(self, temp_db):
        """Test detecting new tracks in playlist."""
        comparator = SyncStateComparator()

        # Create playlist
        playlist = temp_db.create_playlist(
            {"tidal_id": "pl123", "name": "Test Playlist"}
        )

        db_tracks = []
        snapshot_tracks = [
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
                "position": 0,
            },
        ]

        changes = comparator.compare_playlist_tracks(
            db_tracks, snapshot_tracks, playlist.id
        )

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.TRACK_ADDED_TO_PLAYLIST
        assert "Artist 1 - Track 1" in changes[0].new_value
        assert changes[0].playlist_id == playlist.id

    def test_compare_playlist_tracks_removed_track(self, temp_db):
        """Test detecting removed tracks from playlist."""
        comparator = SyncStateComparator()

        # Create playlist and track
        playlist = temp_db.create_playlist(
            {"tidal_id": "pl123", "name": "Test Playlist"}
        )
        track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
            }
        )
        temp_db.add_track_to_playlist(playlist.id, track.id, position=0)

        # Get PlaylistTrack associations with relationships loaded
        db_tracks = temp_db.get_playlist_track_associations(playlist.id)
        snapshot_tracks = []

        changes = comparator.compare_playlist_tracks(
            db_tracks, snapshot_tracks, playlist.id
        )

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.TRACK_REMOVED_FROM_PLAYLIST
        assert "Artist 1 - Track 1" in changes[0].old_value
        assert changes[0].track_id == track.id

    def test_compare_playlist_tracks_moved(self, temp_db):
        """Test detecting track position changes."""
        comparator = SyncStateComparator()

        # Create playlist and track
        playlist = temp_db.create_playlist(
            {"tidal_id": "pl123", "name": "Test Playlist"}
        )
        track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
            }
        )
        temp_db.add_track_to_playlist(playlist.id, track.id, position=0)

        # Get PlaylistTrack associations with relationships loaded
        db_tracks = temp_db.get_playlist_track_associations(playlist.id)
        snapshot_tracks = [
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
                "position": 5,
            },
        ]

        changes = comparator.compare_playlist_tracks(
            db_tracks, snapshot_tracks, playlist.id
        )

        move_changes = [
            c
            for c in changes
            if c.change_type == ChangeType.TRACK_MOVED_WITHIN_PLAYLIST
        ]
        assert len(move_changes) == 1
        assert move_changes[0].old_value == 0
        assert move_changes[0].new_value == 5
        assert move_changes[0].track_id == track.id

    def test_compare_track_metadata(self, temp_db):
        """Test detecting track metadata changes."""
        comparator = SyncStateComparator()

        # Create track
        track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Old Title",
                "artist": "Old Artist",
                "album": "Old Album",
                "year": 2020,
            }
        )

        snapshot_track = {
            "tidal_id": "tr123",
            "title": "New Title",
            "artist": "New Artist",
            "album": "Old Album",
            "year": 2021,
        }

        changes = comparator.compare_track_metadata(track, snapshot_track)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.TRACK_METADATA_CHANGED
        assert changes[0].track_id == track.id

        metadata_changes = changes[0].metadata["changes"]
        assert "title" in metadata_changes
        assert metadata_changes["title"]["old"] == "Old Title"
        assert metadata_changes["title"]["new"] == "New Title"
        assert "artist" in metadata_changes
        assert metadata_changes["year"]["old"] == 2020
        assert metadata_changes["year"]["new"] == 2021
        # Album should not be in changes since it's the same
        assert "album" not in metadata_changes

    def test_compare_track_metadata_no_changes(self, temp_db):
        """Test that no changes are detected when metadata is identical."""
        comparator = SyncStateComparator()

        # Create track
        track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Title",
                "artist": "Artist",
                "album": "Album",
            }
        )

        snapshot_track = {
            "tidal_id": "tr123",
            "title": "Title",
            "artist": "Artist",
            "album": "Album",
        }

        changes = comparator.compare_track_metadata(track, snapshot_track)

        assert len(changes) == 0


class TestChangeType:
    """Test ChangeType enum."""

    def test_change_type_values(self):
        """Test that all change types have correct string values."""
        assert ChangeType.PLAYLIST_ADDED.value == "playlist_added"
        assert ChangeType.PLAYLIST_REMOVED.value == "playlist_removed"
        assert ChangeType.PLAYLIST_RENAMED.value == "playlist_renamed"
        assert ChangeType.TRACK_ADDED_TO_PLAYLIST.value == "track_added_to_playlist"
        assert (
            ChangeType.TRACK_REMOVED_FROM_PLAYLIST.value
            == "track_removed_from_playlist"
        )
        assert (
            ChangeType.TRACK_MOVED_WITHIN_PLAYLIST.value
            == "track_moved_within_playlist"
        )
        assert ChangeType.TRACK_METADATA_CHANGED.value == "track_metadata_changed"
        assert ChangeType.FILE_ADDED.value == "file_added"
        assert ChangeType.FILE_REMOVED.value == "file_removed"
