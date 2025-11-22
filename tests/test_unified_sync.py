"""Tests for unified sync fields in database models and service."""

from datetime import datetime

import pytest

from tidal_cleanup.database import (
    DatabaseService,
    DownloadStatus,
    PlaylistSyncStatus,
    PlaylistTrack,
    TrackSyncStatus,
)


@pytest.fixture
def db_service(tmp_path):
    """Create a temporary database service for testing."""
    db_path = tmp_path / "test_sync.db"
    service = DatabaseService(db_path=db_path)
    service.init_db()
    yield service
    service.close()


@pytest.fixture
def sample_track(db_service):
    """Create a sample track."""
    track = db_service.create_track(
        {
            "tidal_id": "123456",
            "title": "Test Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "normalized_name": "test artist - test track",
        }
    )
    return track


@pytest.fixture
def sample_playlist(db_service):
    """Create a sample playlist."""
    playlist = db_service.create_playlist(
        {
            "tidal_id": "playlist-123",
            "name": "Test Playlist",
            "description": "Test playlist for sync",
        }
    )
    return playlist


class TestEnums:
    """Test the status enum classes."""

    def test_download_status_enum(self):
        """Test DownloadStatus enum values."""
        assert DownloadStatus.NOT_DOWNLOADED.value == "not_downloaded"
        assert DownloadStatus.DOWNLOADING.value == "downloading"
        assert DownloadStatus.DOWNLOADED.value == "downloaded"
        assert DownloadStatus.ERROR.value == "error"

    def test_playlist_sync_status_enum(self):
        """Test PlaylistSyncStatus enum values."""
        assert PlaylistSyncStatus.IN_SYNC.value == "in_sync"
        assert PlaylistSyncStatus.NEEDS_DOWNLOAD.value == "needs_download"
        assert PlaylistSyncStatus.NEEDS_UPDATE.value == "needs_update"
        assert PlaylistSyncStatus.NEEDS_REMOVAL.value == "needs_removal"
        assert PlaylistSyncStatus.UNKNOWN.value == "unknown"

    def test_track_sync_status_enum(self):
        """Test TrackSyncStatus enum values."""
        assert TrackSyncStatus.SYNCED.value == "synced"
        assert TrackSyncStatus.NEEDS_SYMLINK.value == "needs_symlink"
        assert TrackSyncStatus.NEEDS_MOVE.value == "needs_move"
        assert TrackSyncStatus.NEEDS_REMOVAL.value == "needs_removal"
        assert TrackSyncStatus.UNKNOWN.value == "unknown"


class TestTrackModel:
    """Test Track model unified sync fields."""

    def test_track_default_download_status(self, db_service, sample_track):
        """Test track has default download status."""
        assert sample_track.download_status == DownloadStatus.NOT_DOWNLOADED.value
        assert sample_track.download_error is None
        assert sample_track.downloaded_at is None
        assert sample_track.last_verified_at is None

    def test_track_update_download_status(self, db_service, sample_track):
        """Test updating track download status."""
        updated = db_service.update_track_download_status(
            sample_track.id, DownloadStatus.DOWNLOADED.value
        )

        assert updated.download_status == DownloadStatus.DOWNLOADED.value
        assert updated.downloaded_at is not None

    def test_track_download_error(self, db_service, sample_track):
        """Test tracking download errors."""
        error_msg = "Network timeout"
        updated = db_service.update_track_download_status(
            sample_track.id, DownloadStatus.ERROR.value, error=error_msg
        )

        assert updated.download_status == DownloadStatus.ERROR.value
        assert updated.download_error == error_msg

    def test_track_file_path_is_primary(self, db_service):
        """Test that file_path represents primary file location."""
        track = db_service.create_track(
            {
                "tidal_id": "789",
                "title": "Track with File",
                "artist": "Artist",
                "normalized_name": "artist - track with file",
                "file_path": "mp3/Playlists/Playlist A/Artist - Track.mp3",
            }
        )

        assert track.file_path == "mp3/Playlists/Playlist A/Artist - Track.mp3"


class TestPlaylistModel:
    """Test Playlist model unified sync fields."""

    def test_playlist_default_sync_status(self, db_service, sample_playlist):
        """Test playlist has default sync status."""
        assert sample_playlist.sync_status == PlaylistSyncStatus.UNKNOWN.value
        assert sample_playlist.last_updated_tidal is None
        assert sample_playlist.last_synced_filesystem is None

    def test_playlist_update_sync_status(self, db_service, sample_playlist):
        """Test updating playlist sync status."""
        updated = db_service.update_playlist_sync_status(
            sample_playlist.id, PlaylistSyncStatus.IN_SYNC.value
        )

        assert updated.sync_status == PlaylistSyncStatus.IN_SYNC.value
        assert updated.last_synced_filesystem is not None

    def test_playlist_tidal_timestamps(self, db_service, sample_playlist):
        """Test tracking Tidal timestamps."""
        tidal_time = datetime(2025, 11, 20, 10, 0, 0)
        updated = db_service.update_playlist(
            sample_playlist.id, {"last_updated_tidal": tidal_time}
        )

        assert updated.last_updated_tidal == tidal_time


class TestPlaylistTrackModel:
    """Test PlaylistTrack model unified sync fields."""

    def test_playlist_track_default_values(
        self, db_service, sample_playlist, sample_track
    ):
        """Test playlist-track defaults."""
        playlist_track = db_service.add_track_to_playlist(
            sample_playlist.id, sample_track.id
        )

        assert playlist_track.is_primary is False
        assert playlist_track.symlink_path is None
        assert playlist_track.symlink_valid is None
        assert playlist_track.sync_status == TrackSyncStatus.UNKNOWN.value
        assert playlist_track.synced_at is None

    def test_mark_as_primary(self, db_service, sample_playlist, sample_track):
        """Test marking playlist-track as primary."""
        db_service.add_track_to_playlist(sample_playlist.id, sample_track.id)

        updated = db_service.mark_playlist_track_as_primary(
            sample_playlist.id, sample_track.id
        )

        assert updated.is_primary is True
        assert updated.sync_status == TrackSyncStatus.SYNCED.value
        assert updated.synced_at is not None

    def test_update_symlink_status(self, db_service, sample_playlist, sample_track):
        """Test updating symlink information."""
        db_service.add_track_to_playlist(sample_playlist.id, sample_track.id)

        symlink_path = "mp3/Playlists/Playlist B/Artist - Track.mp3"
        updated = db_service.update_symlink_status(
            sample_playlist.id, sample_track.id, symlink_path, valid=True
        )

        assert updated.is_primary is False
        assert updated.symlink_path == symlink_path
        assert updated.symlink_valid is True
        assert updated.sync_status == TrackSyncStatus.SYNCED.value

    def test_broken_symlink(self, db_service, sample_playlist, sample_track):
        """Test tracking broken symlinks."""
        db_service.add_track_to_playlist(sample_playlist.id, sample_track.id)

        symlink_path = "mp3/Playlists/Playlist C/Artist - Track.mp3"
        updated = db_service.update_symlink_status(
            sample_playlist.id, sample_track.id, symlink_path, valid=False
        )

        assert updated.symlink_valid is False
        assert updated.sync_status == TrackSyncStatus.NEEDS_SYMLINK.value


class TestDatabaseServiceHelpers:
    """Test DatabaseService helper methods for unified sync."""

    def test_get_tracks_by_download_status(self, db_service):
        """Test filtering tracks by download status."""
        # Create tracks with different statuses
        track1 = db_service.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "Artist",
                "normalized_name": "artist - track 1",
            }
        )
        track2 = db_service.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "Artist",
                "normalized_name": "artist - track 2",
            }
        )

        db_service.update_track_download_status(
            track2.id, DownloadStatus.DOWNLOADED.value
        )

        not_downloaded = db_service.get_tracks_by_download_status(
            DownloadStatus.NOT_DOWNLOADED.value
        )
        downloaded = db_service.get_tracks_by_download_status(
            DownloadStatus.DOWNLOADED.value
        )

        assert len(not_downloaded) == 1
        assert not_downloaded[0].id == track1.id
        assert len(downloaded) == 1
        assert downloaded[0].id == track2.id

    def test_get_playlists_by_sync_status(self, db_service):
        """Test filtering playlists by sync status."""
        playlist1 = db_service.create_playlist({"tidal_id": "p1", "name": "Playlist 1"})
        playlist2 = db_service.create_playlist({"tidal_id": "p2", "name": "Playlist 2"})

        db_service.update_playlist_sync_status(
            playlist2.id, PlaylistSyncStatus.IN_SYNC.value
        )

        unknown = db_service.get_playlists_by_sync_status(
            PlaylistSyncStatus.UNKNOWN.value
        )
        in_sync = db_service.get_playlists_by_sync_status(
            PlaylistSyncStatus.IN_SYNC.value
        )

        assert len(unknown) == 1
        assert unknown[0].id == playlist1.id
        assert len(in_sync) == 1
        assert in_sync[0].id == playlist2.id

    def test_get_tracks_needing_download(self, db_service):
        """Test getting tracks that need download."""
        track1 = db_service.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "Artist",
                "normalized_name": "artist - track 1",
            }
        )
        track2 = db_service.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "Artist",
                "normalized_name": "artist - track 2",
            }
        )

        db_service.update_track_download_status(
            track2.id, DownloadStatus.DOWNLOADED.value
        )

        needing_download = db_service.get_tracks_needing_download()

        assert len(needing_download) == 1
        assert needing_download[0].id == track1.id

    def test_get_playlists_needing_sync(self, db_service):
        """Test getting playlists that need syncing."""
        p1 = db_service.create_playlist({"tidal_id": "p1", "name": "P1"})
        p2 = db_service.create_playlist({"tidal_id": "p2", "name": "P2"})
        p3 = db_service.create_playlist({"tidal_id": "p3", "name": "P3"})

        db_service.update_playlist_sync_status(
            p1.id, PlaylistSyncStatus.NEEDS_DOWNLOAD.value
        )
        db_service.update_playlist_sync_status(p2.id, PlaylistSyncStatus.IN_SYNC.value)
        db_service.update_playlist_sync_status(
            p3.id, PlaylistSyncStatus.NEEDS_UPDATE.value
        )

        needing_sync = db_service.get_playlists_needing_sync()

        assert len(needing_sync) == 2
        assert p1.id in [p.id for p in needing_sync]
        assert p3.id in [p.id for p in needing_sync]
        assert p2.id not in [p.id for p in needing_sync]

    def test_get_primary_playlist_tracks(self, db_service):
        """Test getting primary playlist tracks."""
        playlist = db_service.create_playlist({"tidal_id": "p1", "name": "P1"})
        track1 = db_service.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "Artist",
                "normalized_name": "artist - track 1",
            }
        )
        track2 = db_service.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "Artist",
                "normalized_name": "artist - track 2",
            }
        )

        db_service.add_track_to_playlist(playlist.id, track1.id)
        db_service.add_track_to_playlist(playlist.id, track2.id)

        db_service.mark_playlist_track_as_primary(playlist.id, track1.id)

        primary = db_service.get_primary_playlist_tracks(playlist.id)

        assert len(primary) == 1
        assert primary[0].track_id == track1.id

    def test_get_duplicate_tracks(self, db_service):
        """Test finding tracks in multiple playlists."""
        p1 = db_service.create_playlist({"tidal_id": "p1", "name": "P1"})
        p2 = db_service.create_playlist({"tidal_id": "p2", "name": "P2"})
        track = db_service.create_track(
            {
                "tidal_id": "1",
                "title": "Track",
                "artist": "Artist",
                "normalized_name": "artist - track",
            }
        )

        db_service.add_track_to_playlist(p1.id, track.id)
        db_service.add_track_to_playlist(p2.id, track.id)

        duplicates = db_service.get_duplicate_tracks()

        assert track.id in duplicates
        assert len(duplicates[track.id]) == 2

    def test_get_sync_statistics(self, db_service):
        """Test getting comprehensive sync statistics."""
        # Create some data
        track1 = db_service.create_track(
            {
                "tidal_id": "1",
                "title": "Track 1",
                "artist": "Artist",
                "normalized_name": "artist - track 1",
            }
        )
        track2 = db_service.create_track(
            {
                "tidal_id": "2",
                "title": "Track 2",
                "artist": "Artist",
                "normalized_name": "artist - track 2",
            }
        )
        db_service.update_track_download_status(
            track2.id, DownloadStatus.DOWNLOADED.value
        )

        playlist = db_service.create_playlist({"tidal_id": "p1", "name": "P1"})
        db_service.update_playlist_sync_status(
            playlist.id, PlaylistSyncStatus.IN_SYNC.value
        )

        db_service.add_track_to_playlist(playlist.id, track1.id)
        db_service.mark_playlist_track_as_primary(playlist.id, track1.id)

        stats = db_service.get_sync_statistics()

        assert stats["tracks"]["total"] == 2
        assert stats["tracks"]["downloaded"] == 1
        assert stats["tracks"]["not_downloaded"] == 1
        assert stats["playlists"]["total"] == 1
        assert stats["playlists"]["in_sync"] == 1
        assert stats["deduplication"]["primary_files"] == 1


class TestDeduplication:
    """Test deduplication scenarios."""

    def test_mark_primary_clears_others(self, db_service):
        """Test that marking one as primary clears others."""
        p1 = db_service.create_playlist({"tidal_id": "p1", "name": "P1"})
        p2 = db_service.create_playlist({"tidal_id": "p2", "name": "P2"})
        track = db_service.create_track(
            {
                "tidal_id": "1",
                "title": "Track",
                "artist": "Artist",
                "normalized_name": "artist - track",
            }
        )

        pt1 = db_service.add_track_to_playlist(p1.id, track.id)
        pt2 = db_service.add_track_to_playlist(p2.id, track.id)

        # Mark first as primary
        db_service.mark_playlist_track_as_primary(p1.id, track.id)

        # Verify
        with db_service.get_session() as session:
            pt1_updated = session.get(PlaylistTrack, pt1.id)
            pt2_updated = session.get(PlaylistTrack, pt2.id)

            assert pt1_updated.is_primary is True
            assert pt2_updated.is_primary is False

        # Mark second as primary
        db_service.mark_playlist_track_as_primary(p2.id, track.id)

        # Verify again
        with db_service.get_session() as session:
            pt1_updated = session.get(PlaylistTrack, pt1.id)
            pt2_updated = session.get(PlaylistTrack, pt2.id)

            assert pt1_updated.is_primary is False
            assert pt2_updated.is_primary is True
