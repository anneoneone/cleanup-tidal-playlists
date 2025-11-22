"""Tests for FilesystemScanner."""

import tempfile
from pathlib import Path

import pytest

from tidal_cleanup.database.filesystem_scanner import FilesystemScanner
from tidal_cleanup.database.models import (
    DownloadStatus,
    Playlist,
    Track,
)
from tidal_cleanup.database.service import DatabaseService


# Helper functions for test data creation
def create_test_track(
    db_service: DatabaseService,
    tidal_id: int = 12345,
    title: str = "Test Track",
    artist_name: str = "Test Artist",
) -> Track:
    """Create a test track in the database."""
    track_data = {
        "tidal_id": str(tidal_id),
        "title": title,
        "artist": artist_name,
        "album": "Test Album",
        "duration": 180,
        "normalized_name": f"{artist_name.lower()} - {title.lower()}",
    }
    return db_service.create_track(track_data)


def create_test_playlist(
    db_service: DatabaseService,
    tidal_uuid: str = "test-playlist-uuid",
    name: str = "Test Playlist",
) -> Playlist:
    """Create a test playlist in the database."""
    playlist_data = {
        "tidal_id": tidal_uuid,
        "name": name,
    }
    return db_service.create_playlist(playlist_data)


def create_test_file(directory: Path, filename: str) -> Path:
    """Create a test file in the given directory."""
    file_path = directory / filename
    file_path.write_text("test content")
    return file_path


def create_test_symlink(directory: Path, link_name: str, target: Path) -> Path:
    """Create a test symlink in the given directory."""
    link_path = directory / link_name
    link_path.symlink_to(target)
    return link_path


def create_playlist_directory(root: Path, playlist_name: str) -> Path:
    """Create a playlist directory structure."""
    playlist_dir = root / "Playlists" / playlist_name
    playlist_dir.mkdir(parents=True, exist_ok=True)
    return playlist_dir


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_service():
    """Create a DatabaseService with temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    # Create service and initialize schema
    service = DatabaseService(f"sqlite:///{db_path}")
    service.init_db()

    yield service

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def filesystem_scanner(db_service: DatabaseService, temp_dir: Path):
    """Create a FilesystemScanner instance."""
    playlists_root = temp_dir / "Playlists"
    playlists_root.mkdir(exist_ok=True)
    return FilesystemScanner(db_service, str(playlists_root))


class TestFilesystemScannerInit:
    """Test FilesystemScanner initialization."""

    def test_init_default_extensions(self, db_service: DatabaseService, temp_dir: Path):
        """Test initialization with default extensions."""
        scanner = FilesystemScanner(db_service, str(temp_dir))
        assert scanner.db_service == db_service
        assert scanner.playlists_root == Path(temp_dir)
        assert ".mp3" in scanner.supported_extensions
        assert ".flac" in scanner.supported_extensions

    def test_init_custom_extensions(self, db_service: DatabaseService, temp_dir: Path):
        """Test initialization with custom extensions."""
        custom_exts = {".mp3", ".wav"}
        scanner = FilesystemScanner(db_service, str(temp_dir), custom_exts)
        assert scanner.supported_extensions == custom_exts


class TestFindPlaylistDirectories:
    """Test _find_playlist_directories method."""

    def test_find_no_directories(self, filesystem_scanner: FilesystemScanner):
        """Test finding playlists when none exist."""
        dirs = filesystem_scanner._find_playlist_directories()
        assert dirs == []

    def test_find_single_playlist(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test finding a single playlist directory."""
        create_playlist_directory(temp_dir, "Test Playlist")
        dirs = filesystem_scanner._find_playlist_directories()
        assert len(dirs) == 1
        assert dirs[0].name == "Test Playlist"

    def test_find_multiple_playlists(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test finding multiple playlist directories."""
        create_playlist_directory(temp_dir, "Playlist 1")
        create_playlist_directory(temp_dir, "Playlist 2")
        create_playlist_directory(temp_dir, "Playlist 3")
        dirs = filesystem_scanner._find_playlist_directories()
        assert len(dirs) == 3
        names = {d.name for d in dirs}
        assert names == {"Playlist 1", "Playlist 2", "Playlist 3"}

    def test_ignore_non_directory_items(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test that non-directory items are ignored."""
        playlists_root = temp_dir / "Playlists"
        playlists_root.mkdir(exist_ok=True)

        # Create a file in Playlists directory (should be ignored)
        (playlists_root / "not_a_directory.txt").write_text("test")

        # Create an actual playlist directory
        create_playlist_directory(temp_dir, "Real Playlist")

        dirs = filesystem_scanner._find_playlist_directories()
        assert len(dirs) == 1
        assert dirs[0].name == "Real Playlist"


class TestFindAudioFiles:
    """Test _find_audio_files method."""

    def test_find_no_files(self, filesystem_scanner: FilesystemScanner, temp_dir: Path):
        """Test finding files in an empty directory."""
        playlist_dir = create_playlist_directory(temp_dir, "Empty")
        files = filesystem_scanner._find_audio_files(playlist_dir)
        assert files == []

    def test_find_audio_files(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test finding audio files."""
        playlist_dir = create_playlist_directory(temp_dir, "Test")

        # Create test files
        create_test_file(playlist_dir, "track1.mp3")
        create_test_file(playlist_dir, "track2.flac")
        create_test_file(playlist_dir, "track3.m4a")

        files = filesystem_scanner._find_audio_files(playlist_dir)
        assert len(files) == 3
        names = {f.name for f in files}
        assert names == {"track1.mp3", "track2.flac", "track3.m4a"}

    def test_ignore_non_audio_files(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test that non-audio files are ignored."""
        playlist_dir = create_playlist_directory(temp_dir, "Test")

        # Create audio and non-audio files
        create_test_file(playlist_dir, "track1.mp3")
        create_test_file(playlist_dir, "readme.txt")
        create_test_file(playlist_dir, "cover.jpg")

        files = filesystem_scanner._find_audio_files(playlist_dir)
        assert len(files) == 1
        assert files[0].name == "track1.mp3"

    def test_find_symlinks(self, filesystem_scanner: FilesystemScanner, temp_dir: Path):
        """Test finding symlinked audio files."""
        playlist_dir = create_playlist_directory(temp_dir, "Test")

        # Create a target file and symlink
        target_dir = temp_dir / "target"
        target_dir.mkdir()
        target = create_test_file(target_dir, "track.mp3")
        create_test_symlink(playlist_dir, "link.mp3", target)

        files = filesystem_scanner._find_audio_files(playlist_dir)
        assert len(files) == 1
        assert files[0].name == "link.mp3"
        assert files[0].is_symlink()


class TestValidateSymlink:
    """Test _validate_symlink method."""

    def test_validate_valid_symlink(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test validating a valid symlink."""
        target_dir = temp_dir / "target"
        target_dir.mkdir()
        target = create_test_file(target_dir, "track.mp3")

        link_dir = temp_dir / "links"
        link_dir.mkdir()
        link = create_test_symlink(link_dir, "link.mp3", target)

        is_valid, target_path = filesystem_scanner._validate_symlink(link)
        assert is_valid is True
        assert target_path.resolve() == target.resolve()

    def test_validate_broken_symlink(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test validating a broken symlink."""
        target = temp_dir / "nonexistent.mp3"

        link_dir = temp_dir / "links"
        link_dir.mkdir()
        link = create_test_symlink(link_dir, "broken.mp3", target)

        is_valid, target_path = filesystem_scanner._validate_symlink(link)
        assert is_valid is False
        assert target_path.resolve() == target.resolve()

    def test_validate_regular_file(
        self, filesystem_scanner: FilesystemScanner, temp_dir: Path
    ):
        """Test validating a regular file (not a symlink)."""
        file = create_test_file(temp_dir, "regular.mp3")

        is_valid, target_path = filesystem_scanner._validate_symlink(file)
        assert is_valid is False
        assert target_path is None


class TestMatchFileToTrack:
    """Test _match_file_to_track method."""

    def test_match_by_artist_title(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test matching file by 'Artist - Title' format."""
        # Create a track with normalized name
        track = create_test_track(
            db_service, title="Test Song", artist_name="Test Artist"
        )

        # Create a file matching the track
        file = temp_dir / "Test Artist - Test Song.mp3"
        file.write_text("test")

        matched = filesystem_scanner._match_file_to_track(file, None)
        assert matched is not None
        assert matched.id == track.id

    def test_match_no_match(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test when no track matches the file."""
        # Create a track
        create_test_track(
            db_service, title="Different Song", artist_name="Different Artist"
        )

        # Create a file that doesn't match
        file = temp_dir / "Unknown Artist - Unknown Song.mp3"
        file.write_text("test")

        matched = filesystem_scanner._match_file_to_track(file, None)
        assert matched is None

    def test_match_by_partial_name(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test matching by partial filename."""
        # Create a track with normalized name
        track = create_test_track(
            db_service, title="Test Song", artist_name="Test Artist"
        )

        # Create a file with partial name (no artist)
        file = temp_dir / "Test Song.mp3"
        file.write_text("test")

        matched = filesystem_scanner._match_file_to_track(file, None)
        # Should match by partial name fallback
        assert matched is not None
        assert matched.id == track.id


class TestProcessSymlink:
    """Test _process_symlink method."""

    def test_process_valid_symlink(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test processing a valid symlink."""
        # Create playlist and track
        playlist = create_test_playlist(db_service, name="Test Playlist")
        track = create_test_track(
            db_service, title="Test Song", artist_name="Test Artist"
        )

        # Add track to playlist
        db_service.add_track_to_playlist(playlist.id, track.id)

        # Create symlink
        target_dir = temp_dir / "target"
        target_dir.mkdir()
        target = target_dir / "Test Artist - Test Song.mp3"
        target.write_text("test")

        link_dir = temp_dir / "links"
        link_dir.mkdir()
        link = create_test_symlink(link_dir, "Test Artist - Test Song.mp3", target)

        # Process symlink
        filesystem_scanner._process_symlink(playlist, link)

        # Verify statistics
        assert filesystem_scanner._stats.symlinks_found == 1
        assert filesystem_scanner._stats.symlinks_valid == 1
        assert filesystem_scanner._stats.playlist_tracks_updated == 1

    def test_process_broken_symlink(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test processing a broken symlink."""
        # Create playlist and track
        playlist = create_test_playlist(db_service, name="Test Playlist")
        track = create_test_track(
            db_service, title="Test Song", artist_name="Test Artist"
        )

        # Add track to playlist
        db_service.add_track_to_playlist(playlist.id, track.id)

        # Create broken symlink
        target = temp_dir / "nonexistent.mp3"
        link_dir = temp_dir / "links"
        link_dir.mkdir()
        link = create_test_symlink(link_dir, "Test Artist - Test Song.mp3", target)

        # Process symlink
        filesystem_scanner._process_symlink(playlist, link)

        # Verify statistics
        assert filesystem_scanner._stats.symlinks_found == 1
        assert filesystem_scanner._stats.symlinks_broken == 1

    def test_process_symlink_no_match(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test processing symlink when no track matches."""
        # Create playlist (no tracks)
        playlist = create_test_playlist(db_service, name="Test Playlist")

        # Create symlink
        target_dir = temp_dir / "target"
        target_dir.mkdir()
        target = create_test_file(target_dir, "Unknown.mp3")

        link_dir = temp_dir / "links"
        link_dir.mkdir()
        link = create_test_symlink(link_dir, "Unknown.mp3", target)

        # Process symlink
        filesystem_scanner._process_symlink(playlist, link)

        # Verify statistics - symlink processed but no updates since no match
        assert filesystem_scanner._stats.symlinks_found == 1
        assert filesystem_scanner._stats.playlist_tracks_updated == 0


class TestProcessRegularFile:
    """Test _process_regular_file method."""

    def test_process_regular_file(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test processing a regular file."""
        # Create playlist and track
        playlist = create_test_playlist(db_service, name="Test Playlist")
        track = create_test_track(
            db_service, title="Test Song", artist_name="Test Artist"
        )

        # Add track to playlist
        db_service.add_track_to_playlist(playlist.id, track.id)

        # Create regular file
        file = temp_dir / "Test Artist - Test Song.mp3"
        file.write_text("test content")

        # Process file
        filesystem_scanner._process_regular_file(playlist, file)

        # Verify track was updated
        updated_track = db_service.get_track_by_id(track.id)
        assert updated_track.file_path is not None
        assert file.name in updated_track.file_path
        assert updated_track.file_size_bytes == len("test content")
        assert updated_track.download_status == DownloadStatus.DOWNLOADED

        # Verify statistics
        assert filesystem_scanner._stats.files_found == 1
        assert filesystem_scanner._stats.tracks_updated == 1
        assert filesystem_scanner._stats.playlist_tracks_updated == 1

    def test_process_regular_file_no_match(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test processing a regular file when no track matches."""
        # Create playlist (no tracks)
        playlist = create_test_playlist(db_service, name="Test Playlist")

        # Create regular file
        file = create_test_file(temp_dir, "Unknown.mp3")

        # Process file
        filesystem_scanner._process_regular_file(playlist, file)

        # Verify statistics - file processed but no updates since no match
        assert filesystem_scanner._stats.files_found == 1
        assert filesystem_scanner._stats.tracks_updated == 0
        assert filesystem_scanner._stats.playlist_tracks_updated == 0


class TestScanAllPlaylists:
    """Test scan_all_playlists method."""

    def test_scan_empty_directory(self, filesystem_scanner: FilesystemScanner):
        """Test scanning when no playlists exist."""
        stats = filesystem_scanner.scan_all_playlists()

        assert stats["playlists_scanned"] == 0
        assert stats["files_found"] == 0
        assert stats["symlinks_found"] == 0

    def test_scan_playlist_with_files(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test scanning a playlist with regular files."""
        # Create playlist and tracks
        playlist = create_test_playlist(db_service, name="Test Playlist")
        track1 = create_test_track(
            db_service, tidal_id=1, title="Song 1", artist_name="Artist 1"
        )
        track2 = create_test_track(
            db_service, tidal_id=2, title="Song 2", artist_name="Artist 2"
        )

        # Add tracks to playlist
        db_service.add_track_to_playlist(playlist.id, track1.id)
        db_service.add_track_to_playlist(playlist.id, track2.id)

        # Create playlist directory and files
        playlist_dir = create_playlist_directory(temp_dir, "Test Playlist")
        create_test_file(playlist_dir, "Artist 1 - Song 1.mp3")
        create_test_file(playlist_dir, "Artist 2 - Song 2.mp3")

        # Scan
        stats = filesystem_scanner.scan_all_playlists()

        # Verify statistics
        assert stats["playlists_scanned"] == 1
        assert stats["files_found"] == 2
        assert stats["tracks_updated"] == 2
        assert stats["playlist_tracks_updated"] == 2

    def test_scan_playlist_with_symlinks(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test scanning a playlist with symlinks."""
        # Create playlist and track
        playlist = create_test_playlist(db_service, name="Test Playlist")
        track = create_test_track(db_service, title="Song", artist_name="Artist")

        # Add track to playlist
        db_service.add_track_to_playlist(playlist.id, track.id)

        # Create target file and symlink
        target_dir = temp_dir / "library"
        target_dir.mkdir()
        target = create_test_file(target_dir, "Artist - Song.mp3")

        playlist_dir = create_playlist_directory(temp_dir, "Test Playlist")
        create_test_symlink(playlist_dir, "Artist - Song.mp3", target)

        # Scan
        stats = filesystem_scanner.scan_all_playlists()

        # Verify statistics
        assert stats["playlists_scanned"] == 1
        assert stats["symlinks_found"] == 1
        assert stats["symlinks_valid"] == 1
        assert stats["playlist_tracks_updated"] == 1

    def test_scan_multiple_playlists(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test scanning multiple playlists."""
        # Create playlists and tracks
        playlist1 = create_test_playlist(
            db_service, tidal_uuid="uuid1", name="Playlist 1"
        )
        playlist2 = create_test_playlist(
            db_service, tidal_uuid="uuid2", name="Playlist 2"
        )

        track1 = create_test_track(
            db_service, tidal_id=1, title="Song 1", artist_name="Artist 1"
        )
        track2 = create_test_track(
            db_service, tidal_id=2, title="Song 2", artist_name="Artist 2"
        )

        # Add tracks to playlists
        db_service.add_track_to_playlist(playlist1.id, track1.id)
        db_service.add_track_to_playlist(playlist2.id, track2.id)

        # Create playlist directories and files
        dir1 = create_playlist_directory(temp_dir, "Playlist 1")
        create_test_file(dir1, "Artist 1 - Song 1.mp3")

        dir2 = create_playlist_directory(temp_dir, "Playlist 2")
        create_test_file(dir2, "Artist 2 - Song 2.mp3")

        # Scan
        stats = filesystem_scanner.scan_all_playlists()

        # Verify statistics
        assert stats["playlists_scanned"] == 2
        assert stats["files_found"] == 2


class TestGetScanStatistics:
    """Test get_scan_statistics method."""

    def test_get_statistics_initial(self, filesystem_scanner: FilesystemScanner):
        """Test getting statistics before any scan."""
        stats = filesystem_scanner.get_scan_statistics()

        assert stats["playlists_scanned"] == 0
        assert stats["files_found"] == 0
        assert stats["symlinks_found"] == 0
        assert stats["symlinks_valid"] == 0
        assert stats["symlinks_broken"] == 0
        assert stats["tracks_updated"] == 0
        assert stats["playlist_tracks_updated"] == 0
        assert stats["errors"] == []

    def test_get_statistics_after_scan(
        self,
        filesystem_scanner: FilesystemScanner,
        db_service: DatabaseService,
        temp_dir: Path,
    ):
        """Test getting statistics after a scan."""
        # Create playlist and track
        playlist = create_test_playlist(db_service, name="Test")
        track = create_test_track(db_service)
        db_service.add_track_to_playlist(playlist.id, track.id)

        # Create file
        playlist_dir = create_playlist_directory(temp_dir, "Test")
        create_test_file(playlist_dir, "Test Artist - Test Track.mp3")

        # Scan
        filesystem_scanner.scan_all_playlists()

        # Get statistics
        stats = filesystem_scanner.get_scan_statistics()

        assert stats["playlists_scanned"] == 1
        assert stats["files_found"] == 1
        assert stats["tracks_updated"] == 1
