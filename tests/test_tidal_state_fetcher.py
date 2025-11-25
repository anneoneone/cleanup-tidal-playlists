"""Tests for TidalStateFetcher service."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from tidal_cleanup.core.tidal.state_fetcher import TidalStateFetcher
from tidal_cleanup.database import DatabaseService, DownloadStatus, PlaylistSyncStatus


@pytest.fixture
def db_service(tmp_path):
    """Create a temporary database service for testing."""
    db_path = tmp_path / "test_tidal_fetcher.db"
    service = DatabaseService(db_path=db_path)
    service.init_db()
    yield service
    service.close()


@pytest.fixture
def mock_tidal_session():
    """Create mock Tidal session."""
    session = Mock()
    session.user = Mock()
    return session


@pytest.fixture
def tidal_fetcher(db_service, mock_tidal_session):
    """Create TidalStateFetcher instance."""
    return TidalStateFetcher(db_service, mock_tidal_session)


def create_mock_artist(artist_id=100, name="Test Artist"):
    """Create a mock Tidal artist."""
    artist = Mock()
    artist.id = artist_id
    artist.name = name
    return artist


def create_mock_album(album_id="album-123", name="Test Album", artist=None):
    """Create a mock Tidal album."""
    album = Mock()
    album.id = album_id
    album.name = name
    album.artist = artist
    album.upc = None
    album.release_date = None
    return album


def create_mock_track(
    track_id=1000,
    name="Test Track",
    artist=None,
    album=None,
    duration=240,
    track_number=1,
):
    """Create a mock Tidal track."""
    if artist is None:
        artist = create_mock_artist()

    # Use spec=[] to prevent automatic Mock creation for undefined attributes
    track = Mock(spec=[])
    track.id = track_id
    track.name = name
    track.artist = artist
    track.album = album
    track.duration = duration
    track.track_number = track_number
    track.volume_number = None
    track.year = None
    track.popularity = None
    track.explicit = False
    track.isrc = None
    track.copyright = None
    track.version = None
    return track


def create_mock_playlist(
    playlist_id="pl-123",
    name="Test Playlist",
    description="Test Description",
    num_tracks=0,
    tracks=None,
):
    """Create a mock Tidal playlist."""
    playlist = Mock()
    playlist.id = playlist_id
    playlist.uuid = playlist_id
    playlist.name = name
    playlist.description = description
    playlist.num_tracks = num_tracks
    playlist.creator_name = None
    playlist.creator_id = None
    playlist.duration = None
    playlist.num_videos = None
    playlist.popularity = None
    playlist.public = None
    playlist.picture_url = None
    playlist.square_picture_url = None
    playlist.share_url = None
    playlist.listen_url = None
    playlist.created = None
    playlist.last_updated = None
    playlist.last_item_added_at = None

    if tracks is None:
        tracks = []
    playlist.tracks = Mock(return_value=tracks)

    return playlist


def create_mock_playlist_minimal(
    playlist_id="pl-123",
    name="Test Playlist",
):
    """Create a minimal mock Tidal playlist with None for optional fields."""
    playlist = Mock()
    playlist.id = playlist_id
    playlist.uuid = playlist_id
    playlist.name = name
    playlist.description = None
    playlist.num_tracks = 0
    playlist.creator_name = None
    playlist.creator_id = None
    playlist.duration = None
    playlist.num_videos = None
    playlist.popularity = None
    playlist.public = None
    playlist.picture_url = None
    playlist.square_picture_url = None
    playlist.share_url = None
    playlist.listen_url = None
    playlist.created = None
    playlist.last_updated = None
    playlist.last_item_added_at = None
    playlist.tracks = Mock(return_value=[])
    return playlist


class TestTidalStateFetcherInit:
    """Test TidalStateFetcher initialization."""

    def test_init(self, db_service, mock_tidal_session):
        """Test initialization."""
        fetcher = TidalStateFetcher(db_service, mock_tidal_session)
        assert fetcher.db_service == db_service
        assert fetcher.tidal_session == mock_tidal_session
        assert fetcher._fetched_playlist_ids == []
        # Check stats is FetchStatistics instance
        assert hasattr(fetcher._stats, "playlists_fetched")
        assert fetcher._stats.playlists_fetched == 0


class TestConvertTidalPlaylist:
    """Test _convert_tidal_playlist method."""

    def test_convert_basic_playlist(self, tidal_fetcher):
        """Test converting basic playlist."""
        tidal_playlist = create_mock_playlist(
            playlist_id="test-123",
            name="Test Playlist",
            description="Test Description",
        )

        result = tidal_fetcher._convert_tidal_playlist(tidal_playlist)

        assert result["tidal_id"] == "test-123"
        assert result["name"] == "Test Playlist"
        assert result["description"] == "Test Description"

    def test_convert_playlist_without_optional_fields(self, tidal_fetcher):
        """Test converting playlist without optional fields."""
        tidal_playlist = create_mock_playlist_minimal(
            playlist_id="test-456",
            name="Minimal Playlist",
        )

        result = tidal_fetcher._convert_tidal_playlist(tidal_playlist)

        assert result["tidal_id"] == "test-456"
        assert result["name"] == "Minimal Playlist"
        assert result["description"] is None


class TestConvertTidalTrack:
    """Test _convert_tidal_track method."""

    def test_convert_basic_track(self, tidal_fetcher):
        """Test converting basic track."""
        artist = create_mock_artist(100, "Artist Name")
        album = create_mock_album("album-200", "Album Name", artist=artist)
        track = create_mock_track(
            track_id=1000,
            name="Track Name",
            artist=artist,
            album=album,
            duration=240,
            track_number=5,
        )

        result = tidal_fetcher._convert_tidal_track(track)

        assert result["tidal_id"] == "1000"
        assert result["title"] == "Track Name"
        assert result["artist"] == "Artist Name"
        assert result["album"] == "Album Name"
        assert result["album_artist"] == "Artist Name"
        assert result["duration"] == 240
        assert result["track_number"] == 5
        assert result["normalized_name"] == "artist name - track name"

    def test_convert_track_without_album(self, tidal_fetcher):
        """Test converting track without album."""
        artist = create_mock_artist(100, "Artist Name")
        track = create_mock_track(
            track_id=3000,
            name="Single Track",
            artist=artist,
            album=None,
        )

        result = tidal_fetcher._convert_tidal_track(track)

        assert result["album"] is None
        assert "album_artist" not in result

    def test_convert_track_with_explicit_flag(self, tidal_fetcher):
        """Test converting track with explicit flag."""
        artist = create_mock_artist(100, "Artist Name")
        track = create_mock_track(
            track_id=4000,
            name="Explicit Track",
            artist=artist,
        )
        track.explicit = True
        track.isrc = "US1234567890"

        result = tidal_fetcher._convert_tidal_track(track)

        assert result["explicit"] is True
        assert result["isrc"] == "US1234567890"


class TestCreatePlaylist:
    """Test _create_playlist method."""

    def test_create_new_playlist(self, tidal_fetcher):
        """Test creating new playlist."""
        playlist_data = {
            "tidal_id": "new-playlist",
            "name": "New Playlist",
            "description": "Test",
            "num_tracks": 5,
        }

        playlist = tidal_fetcher._create_playlist(playlist_data, mark_needs_sync=True)

        assert playlist.tidal_id == "new-playlist"
        assert playlist.name == "New Playlist"
        assert playlist.sync_status == PlaylistSyncStatus.NEEDS_DOWNLOAD.value

    def test_create_playlist_without_sync_marking(self, tidal_fetcher):
        """Test creating playlist without marking for sync."""
        playlist_data = {
            "tidal_id": "new-playlist-2",
            "name": "New Playlist 2",
        }

        playlist = tidal_fetcher._create_playlist(playlist_data, mark_needs_sync=False)

        assert playlist.sync_status == PlaylistSyncStatus.UNKNOWN.value


class TestUpdatePlaylist:
    """Test _update_playlist method."""

    def test_update_playlist_no_changes(self, tidal_fetcher, db_service):
        """Test updating playlist with no changes."""
        # Create existing playlist
        existing = db_service.create_playlist(
            {
                "tidal_id": "existing-123",
                "name": "Existing Playlist",
                "last_updated_tidal": datetime(2024, 1, 1, 12, 0, 0),
                "sync_status": PlaylistSyncStatus.IN_SYNC.value,
            }
        )

        playlist_data = {
            "tidal_id": "existing-123",
            "name": "Existing Playlist",
            "last_updated_tidal": datetime(2024, 1, 1, 12, 0, 0),
        }

        updated, was_updated = tidal_fetcher._update_playlist(
            existing, playlist_data, mark_needs_sync=True
        )

        assert updated.sync_status == PlaylistSyncStatus.IN_SYNC.value
        assert was_updated is False  # No changes, so not updated

    def test_update_playlist_with_changes(self, tidal_fetcher, db_service):
        """Test updating playlist with changes."""
        # Create existing playlist
        existing = db_service.create_playlist(
            {
                "tidal_id": "existing-456",
                "name": "Old Name",
                "last_updated_tidal": datetime(2024, 1, 1, 12, 0, 0),
                "sync_status": PlaylistSyncStatus.IN_SYNC.value,
            }
        )

        playlist_data = {
            "tidal_id": "existing-456",
            "name": "New Name",
            "last_updated_tidal": datetime(2024, 1, 15, 12, 0, 0),
        }

        updated, was_updated = tidal_fetcher._update_playlist(
            existing, playlist_data, mark_needs_sync=True
        )

        assert updated.name == "New Name"
        assert updated.sync_status == PlaylistSyncStatus.NEEDS_UPDATE.value
        assert was_updated is True  # Playlist changed, so it was updated


class TestCreateTrack:
    """Test _create_track method."""

    def test_create_new_track(self, tidal_fetcher):
        """Test creating new track."""
        track_data = {
            "tidal_id": "track-123",
            "title": "New Track",
            "artist": "Artist Name",
            "normalized_name": "artist name - new track",
        }

        track = tidal_fetcher._create_track(track_data)

        assert track.tidal_id == "track-123"
        assert track.title == "New Track"
        assert track.artist == "Artist Name"
        assert track.download_status == DownloadStatus.NOT_DOWNLOADED.value


class TestUpdateTrack:
    """Test _update_track method."""

    def test_update_track_no_changes(self, tidal_fetcher, db_service):
        """Test updating track with no changes."""
        existing = db_service.create_track(
            {
                "tidal_id": "track-456",
                "title": "Existing Track",
                "artist": "Artist Name",
                "normalized_name": "artist name - existing track",
            }
        )

        track_data = {
            "tidal_id": "track-456",
            "title": "Existing Track",
            "artist": "Artist Name",
            "normalized_name": "artist name - existing track",
        }

        updated = tidal_fetcher._update_track(existing, track_data)

        assert updated.title == "Existing Track"

    def test_update_track_with_changes(self, tidal_fetcher, db_service):
        """Test updating track with changes."""
        existing = db_service.create_track(
            {
                "tidal_id": "track-789",
                "title": "Old Title",
                "artist": "Artist Name",
                "normalized_name": "artist name - old title",
            }
        )

        track_data = {
            "tidal_id": "track-789",
            "title": "New Title",
            "artist": "Artist Name",
            "normalized_name": "artist name - new title",
            "duration": 240,
        }

        updated = tidal_fetcher._update_track(existing, track_data)

        assert updated.title == "New Title"
        assert updated.duration == 240


class TestFetchPlaylistTracks:
    """Test _fetch_playlist_tracks method."""

    def test_fetch_tracks_for_new_playlist(self, tidal_fetcher, db_service):
        """Test fetching tracks for new playlist."""
        # Create playlist
        db_playlist = db_service.create_playlist(
            {
                "tidal_id": "playlist-new",
                "name": "New Playlist",
            }
        )

        # Create mock Tidal playlist with tracks
        artist = create_mock_artist(100, "Artist")
        track1 = create_mock_track(1001, "Track 1", artist)
        track2 = create_mock_track(1002, "Track 2", artist)

        tidal_playlist = create_mock_playlist(
            playlist_id="playlist-new",
            name="New Playlist",
            tracks=[track1, track2],
        )

        stats = tidal_fetcher._fetch_playlist_tracks(tidal_playlist, db_playlist)

        assert stats["created"] == 2
        assert stats["updated"] == 0

        # Check tracks were created
        tracks = db_service.get_all_tracks()
        assert len(tracks) == 2

        # Check playlist-track relationships exist
        # Note: get_playlist_tracks returns Track objects, not PlaylistTrack
        playlist_tracks = db_service.get_playlist_tracks(db_playlist.id)
        assert len(playlist_tracks) == 2


class TestFetchAllPlaylists:
    """Test fetch_all_playlists method."""

    def test_fetch_empty_playlists(self, tidal_fetcher, mock_tidal_session):
        """Test fetching when user has no playlists."""
        mock_tidal_session.user.playlists.return_value = []

        playlists = tidal_fetcher.fetch_all_playlists()

        assert len(playlists) == 0

        stats = tidal_fetcher.get_fetch_statistics()
        assert stats["playlists_fetched"] == 0
        assert stats["playlists_created"] == 0

    def test_fetch_multiple_playlists(self, tidal_fetcher, mock_tidal_session):
        """Test fetching multiple playlists."""
        # Create mock playlists
        playlist1 = create_mock_playlist("pl-1", "Playlist 1")
        playlist2 = create_mock_playlist("pl-2", "Playlist 2")
        mock_tidal_session.user.playlists.return_value = [playlist1, playlist2]

        playlists = tidal_fetcher.fetch_all_playlists(mark_needs_sync=False)

        assert len(playlists) == 2
        assert playlists[0].tidal_id == "pl-1"
        assert playlists[1].tidal_id == "pl-2"

        stats = tidal_fetcher.get_fetch_statistics()
        assert stats["playlists_created"] == 2
        assert stats["playlists_fetched"] == 2

    def test_fetch_marks_playlists_for_sync(self, tidal_fetcher, mock_tidal_session):
        """Test that new playlists are marked for sync."""
        playlist = create_mock_playlist("pl-sync", "Sync Playlist")
        mock_tidal_session.user.playlists.return_value = [playlist]

        playlists = tidal_fetcher.fetch_all_playlists(mark_needs_sync=True)

        assert len(playlists) == 1
        assert playlists[0].sync_status == PlaylistSyncStatus.NEEDS_DOWNLOAD.value

    def test_fetch_with_error(self, tidal_fetcher, mock_tidal_session):
        """Test fetch with error in playlist processing."""
        # Create one good playlist and one that will fail
        good_playlist = create_mock_playlist("pl-good", "Good Playlist")
        bad_playlist = create_mock_playlist("pl-bad", "Bad Playlist")
        # Make bad playlist raise exception when accessing id
        type(bad_playlist).id = property(lambda self: 1 / 0)

        mock_tidal_session.user.playlists.return_value = [good_playlist, bad_playlist]

        playlists = tidal_fetcher.fetch_all_playlists()

        # Should get 1 playlist (the good one)
        assert len(playlists) == 1
        assert playlists[0].tidal_id == "pl-good"

        stats = tidal_fetcher.get_fetch_statistics()
        assert stats["playlists_created"] == 1
        assert stats["playlists_skipped"] == 1
        assert stats["error_count"] == 1

    def test_fetch_creates_snapshot(
        self, tidal_fetcher, db_service, mock_tidal_session
    ):
        """Test that fetch_all_playlists creates a sync snapshot."""
        # Create mock playlists
        playlist1 = create_mock_playlist("pl-1", "Playlist 1")
        mock_tidal_session.user.playlists.return_value = [playlist1]

        # Verify no snapshots exist yet
        assert db_service.get_latest_snapshot("tidal_sync") is None

        # Fetch playlists
        tidal_fetcher.fetch_all_playlists()

        # Verify snapshot was created
        snapshot = db_service.get_latest_snapshot("tidal_sync")
        assert snapshot is not None
        assert snapshot.snapshot_type == "tidal_sync"

        # Verify snapshot data
        import json

        data = json.loads(snapshot.snapshot_data)
        assert data["status"] == "completed"
        assert data["playlists_fetched"] == 1
        assert data["playlists_created"] == 1

    def test_fetch_optimization_skips_unchanged_playlists(
        self, tidal_fetcher, db_service, mock_tidal_session
    ):
        """Test that second fetch skips unchanged playlists."""
        from datetime import datetime, timezone

        # Create mock playlist with timestamp
        playlist = create_mock_playlist("pl-1", "Playlist 1")
        playlist.last_updated = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_tidal_session.user.playlists.return_value = [playlist]

        # First fetch - creates playlist
        tidal_fetcher.fetch_all_playlists()
        stats1 = tidal_fetcher.get_fetch_statistics()
        assert stats1["playlists_created"] == 1
        assert stats1["playlists_skipped"] == 0

        # Second fetch - should skip unchanged playlist
        tidal_fetcher.fetch_all_playlists()
        stats2 = tidal_fetcher.get_fetch_statistics()
        assert stats2["playlists_created"] == 0
        assert stats2["playlists_updated"] == 0
        assert stats2["playlists_skipped"] == 1


class TestMarkRemovedPlaylists:
    """Test mark_removed_playlists method."""

    def test_mark_removed_playlists(
        self, tidal_fetcher, db_service, mock_tidal_session
    ):
        """Test marking playlists removed from Tidal."""
        # Create playlists in database
        db_service.create_playlist(
            {
                "tidal_id": "keep-1",
                "name": "Keep 1",
                "sync_status": PlaylistSyncStatus.IN_SYNC.value,
            }
        )
        db_service.create_playlist(
            {
                "tidal_id": "remove-1",
                "name": "Remove 1",
                "sync_status": PlaylistSyncStatus.IN_SYNC.value,
            }
        )
        db_service.create_playlist(
            {
                "tidal_id": "keep-2",
                "name": "Keep 2",
                "sync_status": PlaylistSyncStatus.IN_SYNC.value,
            }
        )

        # Simulate fetch finding only keep-1 and keep-2
        playlist1 = create_mock_playlist("keep-1", "Keep 1")
        playlist2 = create_mock_playlist("keep-2", "Keep 2")
        mock_tidal_session.user.playlists.return_value = [playlist1, playlist2]

        # Fetch to populate fetched IDs
        tidal_fetcher.fetch_all_playlists()

        # Now mark removed
        count = tidal_fetcher.mark_removed_playlists()

        assert count == 1

        # Check that remove-1 is marked for removal
        removed = db_service.get_playlist_by_tidal_id("remove-1")
        assert removed.sync_status == PlaylistSyncStatus.NEEDS_REMOVAL.value

        # Check that others remain IN_SYNC (fetch was called without mark_needs_sync)
        kept1 = db_service.get_playlist_by_tidal_id("keep-1")
        kept2 = db_service.get_playlist_by_tidal_id("keep-2")
        assert kept1.sync_status == PlaylistSyncStatus.IN_SYNC.value
        assert kept2.sync_status == PlaylistSyncStatus.IN_SYNC.value

    def test_mark_removed_without_fetch(self, tidal_fetcher):
        """Test marking removed playlists without prior fetch."""
        count = tidal_fetcher.mark_removed_playlists()

        assert count == 0  # Should return 0 with warning


class TestGetFetchStatistics:
    """Test get_fetch_statistics method."""

    def test_get_statistics(self, tidal_fetcher):
        """Test getting fetch statistics."""
        # Manually set some stats
        tidal_fetcher._stats.playlists_created = 5
        tidal_fetcher._stats.playlists_updated = 3
        tidal_fetcher._stats.tracks_created = 100
        tidal_fetcher._stats.tracks_updated = 20
        tidal_fetcher._stats.errors.append("Test error")

        stats = tidal_fetcher.get_fetch_statistics()

        assert stats["playlists_created"] == 5
        assert stats["playlists_updated"] == 3
        assert stats["tracks_created"] == 100
        assert stats["tracks_updated"] == 20
        assert stats["error_count"] == 1
        assert "Test error" in stats["errors"]

    def test_statistics_after_fetch(self, tidal_fetcher, mock_tidal_session):
        """Test statistics after actual fetch."""
        playlist = create_mock_playlist("pl-1", "Test Playlist")
        mock_tidal_session.user.playlists.return_value = [playlist]

        tidal_fetcher.fetch_all_playlists()

        stats = tidal_fetcher.get_fetch_statistics()
        assert stats["playlists_fetched"] == 1
        assert stats["playlists_created"] == 1
        assert stats["playlists_updated"] == 0
        assert stats["playlists_skipped"] == 0


class TestTidalStateFetcherEdgeCases:
    """Test edge cases and error handling."""

    def test_fetch_without_tidal_session(self, db_service):
        """Test error when no Tidal session provided."""
        fetcher = TidalStateFetcher(db_service, tidal_session=None)

        with pytest.raises(RuntimeError, match="Tidal session required"):
            fetcher.fetch_all_playlists()

    def test_fetch_playlists_api_error(self, tidal_fetcher, mock_tidal_session):
        """Test handling API error when fetching playlists."""
        mock_tidal_session.user.playlists.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            tidal_fetcher.fetch_all_playlists()

    def test_fetch_tracks_error_continues(
        self, tidal_fetcher, db_service, mock_tidal_session
    ):
        """Test that error in track processing doesn't stop the fetch."""
        # Create a playlist first
        playlist_data = {
            "tidal_id": "pl-error",
            "name": "Error Playlist",
            "num_tracks": 2,
        }
        db_playlist = db_service.create_playlist(playlist_data)

        # Mock track that will cause an error
        artist = create_mock_artist()
        album = create_mock_album(artist=artist)
        track1 = create_mock_track(track_id=1, name="Good Track", album=album)

        # Create a mock that will fail when converting
        track2 = Mock()
        track2.id = 2
        track2.name = None  # Missing required field
        track2.artist = None  # This will cause an error

        mock_tidal_playlist = Mock()
        mock_tidal_playlist.tracks.return_value = [track1, track2]

        # Fetch should not raise but should log error
        stats = tidal_fetcher._fetch_playlist_tracks(mock_tidal_playlist, db_playlist)

        # Should have processed at least the good track
        assert stats["created"] >= 1

    def test_extract_track_metadata_with_release_date(self, tidal_fetcher):
        """Test extracting track with release date."""
        artist = create_mock_artist()
        album = create_mock_album(artist=artist)

        track = Mock()
        track.id = 1000
        track.name = "Test Track"
        track.artist = artist
        track.album = album
        track.duration = 240
        track.track_number = 1
        track.volume_number = None
        track.year = None
        track.popularity = None
        track.explicit = False
        track.isrc = None
        track.copyright = None
        track.version = None
        track.tidal_release_date = "2023-01-15"

        track_data = tidal_fetcher._convert_tidal_track(track)

        assert track_data["tidal_release_date"] == "2023-01-15"

    def test_extract_album_metadata_with_upc(self, tidal_fetcher):
        """Test extracting album metadata with UPC."""
        artist = create_mock_artist()

        album = Mock()
        album.id = "album-123"
        album.name = "Test Album"
        album.artist = artist
        album.upc = "123456789012"
        album.release_date = "2023-01-01"

        track = Mock()
        track.id = 1000
        track.name = "Test Track"
        track.artist = artist
        track.album = album
        track.duration = 240
        track.track_number = 1
        track.volume_number = None
        track.year = None
        track.popularity = None
        track.explicit = False
        track.isrc = None
        track.copyright = None
        track.version = None

        track_data = tidal_fetcher._convert_tidal_track(track)

        assert track_data["album_upc"] == "123456789012"
        assert track_data["album_release_date"] == "2023-01-01"

    def test_extract_album_cover_url(self, tidal_fetcher):
        """Test extracting album cover URL."""
        artist = create_mock_artist()

        album = Mock()
        album.id = "abc123"
        album.name = "Test Album"
        album.artist = artist
        album.upc = None
        album.release_date = None

        track = Mock()
        track.id = 1000
        track.name = "Test Track"
        track.artist = artist
        track.album = album
        track.duration = 240
        track.track_number = 1
        track.volume_number = None
        track.year = None
        track.popularity = None
        track.explicit = False
        track.isrc = None
        track.copyright = None
        track.version = None

        track_data = tidal_fetcher._convert_tidal_track(track)

        assert "album_cover_url" in track_data
        assert "abc123" in track_data["album_cover_url"]

    def test_extract_audio_metadata(self, tidal_fetcher):
        """Test extracting audio quality metadata."""
        artist = create_mock_artist()
        album = create_mock_album(artist=artist)

        track = Mock()
        track.id = 1000
        track.name = "Test Track"
        track.artist = artist
        track.album = album
        track.duration = 240
        track.track_number = 1
        track.volume_number = None
        track.year = None
        track.popularity = None
        track.explicit = False
        track.isrc = None
        track.copyright = None
        track.version = None
        track.audio_quality = "HI_RES"
        track.audio_modes = ["STEREO", "DOLBY_ATMOS"]

        track_data = tidal_fetcher._convert_tidal_track(track)

        assert track_data["audio_quality"] == "HI_RES"
        assert "STEREO" in track_data["audio_modes"]

    def test_update_playlist_timezone_aware(self, tidal_fetcher, db_service):
        """Test updating playlist with timezone-aware timestamps."""
        from datetime import timezone

        # Create existing playlist with naive datetime
        playlist_data = {
            "tidal_id": "pl-tz",
            "name": "Timezone Test",
            "last_updated_tidal": datetime(2023, 1, 1, 12, 0, 0),
        }
        existing = db_service.create_playlist(playlist_data)

        # Update with newer timezone-aware timestamp
        new_data = {
            "tidal_id": "pl-tz",
            "name": "Timezone Test Updated",
            "last_updated_tidal": datetime(2023, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

        updated, was_updated = tidal_fetcher._update_playlist(
            existing, new_data, mark_needs_sync=True
        )

        assert was_updated is True
        assert updated.name == "Timezone Test Updated"

    def test_update_playlist_new_timestamp_no_old(self, tidal_fetcher, db_service):
        """Test updating playlist when new has timestamp but old doesn't."""
        from datetime import timezone

        # Create existing playlist without timestamp
        playlist_data = {
            "tidal_id": "pl-no-old",
            "name": "No Old Timestamp",
            "last_updated_tidal": None,
        }
        existing = db_service.create_playlist(playlist_data)

        # Update with timestamp
        new_data = {
            "tidal_id": "pl-no-old",
            "name": "No Old Timestamp",
            "last_updated_tidal": datetime(2023, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

        updated, was_updated = tidal_fetcher._update_playlist(
            existing, new_data, mark_needs_sync=True
        )

        assert was_updated is True
