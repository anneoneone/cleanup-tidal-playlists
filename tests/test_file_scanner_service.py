"""Tests for FileScannerService."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from tidal_cleanup.database import DatabaseService
from tidal_cleanup.database.file_scanner_service import FileScannerService


# Helper functions
def create_test_track(
    db_service: DatabaseService,
    tidal_id: str = "123456",
    title: str = "Test Track",
    artist: str = "Test Artist",
    album: str = "Test Album",
    isrc: str = None,
    file_path: str = None,
    file_hash: str = None,
) -> int:
    """Create a test track and return its ID."""
    track_data = {
        "tidal_id": tidal_id,
        "title": title,
        "artist": artist,
        "album": album,
        "duration": 180,
        "normalized_name": f"{artist} - {title}",
    }
    if isrc:
        track_data["isrc"] = isrc
    if file_path:
        track_data["file_path"] = file_path
    if file_hash:
        track_data["file_hash"] = file_hash

    track = db_service.create_track(track_data)
    return track.id


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_service(temp_dir):
    """Create a DatabaseService with a temporary database."""
    db_path = temp_dir / "test.db"
    service = DatabaseService(db_path=str(db_path))
    service.init_db()
    yield service
    service.close()


@pytest.fixture
def scanner(db_service):
    """Create a FileScannerService instance."""
    return FileScannerService(db_service)


class TestFileScannerInit:
    """Test FileScannerService initialization."""

    def test_init_default_extensions(self, db_service):
        """Test initialization with default extensions."""
        scanner = FileScannerService(db_service)
        assert scanner.db_service is db_service
        assert ".mp3" in scanner.supported_extensions
        assert ".flac" in scanner.supported_extensions
        assert ".m4a" in scanner.supported_extensions

    def test_init_custom_extensions(self, db_service):
        """Test initialization with custom extensions."""
        custom_exts = (".mp3", ".wav")
        scanner = FileScannerService(db_service, supported_extensions=custom_exts)
        assert scanner.supported_extensions == custom_exts


class TestScanDirectory:
    """Test scan_directory method."""

    def test_scan_directory_not_exists(self, scanner, temp_dir):
        """Test error when directory doesn't exist."""
        fake_dir = temp_dir / "nonexistent"
        with pytest.raises(ValueError, match="does not exist"):
            scanner.scan_directory(fake_dir)

    def test_scan_directory_not_dir(self, scanner, temp_dir):
        """Test error when path is not a directory."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")
        with pytest.raises(ValueError, match="not a directory"):
            scanner.scan_directory(file_path)

    def test_scan_empty_directory(self, scanner, temp_dir):
        """Test scanning empty directory."""
        result = scanner.scan_directory(temp_dir)

        assert result["total_files"] == 0
        assert result["matched"] == []
        assert result["unmatched_files"] == []
        assert len(result["orphaned_tracks"]) == 0

    def test_scan_directory_with_audio_files_no_db_tracks(self, scanner, temp_dir):
        """Test scanning directory with audio files but no database tracks."""
        # Create some audio files
        (temp_dir / "song1.mp3").write_text("audio data")
        (temp_dir / "song2.flac").write_text("audio data")

        result = scanner.scan_directory(temp_dir)

        assert result["total_files"] == 2
        assert len(result["unmatched_files"]) == 2
        assert result["matched"] == []

    def test_scan_directory_with_matched_files(self, scanner, db_service, temp_dir):
        """Test scanning with files that match database tracks."""
        # Create audio file
        audio_file = temp_dir / "song.mp3"
        audio_file.write_text("audio data")

        # Create track in DB with this file path
        track_id = create_test_track(
            db_service, title="Song", artist="Artist", file_path=str(audio_file)
        )

        result = scanner.scan_directory(temp_dir, update_db=False)

        assert result["total_files"] == 1
        assert len(result["matched"]) == 1
        assert result["matched"][0][0] == audio_file
        assert result["matched"][0][1].id == track_id
        assert len(result["unmatched_files"]) == 0

    def test_scan_directory_with_orphaned_tracks(self, scanner, db_service, temp_dir):
        """Test scanning directory identifies orphaned tracks."""
        # Create track in DB but no file
        create_test_track(db_service, title="Orphan", artist="Artist")

        result = scanner.scan_directory(temp_dir)

        assert result["total_files"] == 0
        assert len(result["orphaned_tracks"]) == 1
        assert result["orphaned_tracks"][0].title == "Orphan"

    def test_scan_directory_update_db(self, scanner, db_service, temp_dir):
        """Test that update_db=True updates track file info."""
        audio_file = temp_dir / "song.mp3"
        audio_file.write_text("audio data")

        create_test_track(
            db_service, title="Song", artist="Artist", file_path=str(audio_file)
        )

        with patch.object(scanner, "_update_track_file_info") as mock_update:
            scanner.scan_directory(temp_dir, update_db=True)
            assert mock_update.call_count == 1


class TestFindAudioFiles:
    """Test _find_audio_files method."""

    def test_find_audio_files_single_level(self, scanner, temp_dir):
        """Test finding audio files in single directory."""
        (temp_dir / "song1.mp3").write_text("data")
        (temp_dir / "song2.flac").write_text("data")
        (temp_dir / "ignore.txt").write_text("data")

        files = scanner._find_audio_files(temp_dir)

        assert len(files) == 2
        assert all(f.suffix in scanner.supported_extensions for f in files)

    def test_find_audio_files_recursive(self, scanner, temp_dir):
        """Test finding audio files recursively."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()

        (temp_dir / "song1.mp3").write_text("data")
        (subdir / "song2.mp3").write_text("data")

        files = scanner._find_audio_files(temp_dir)

        assert len(files) == 2

    def test_find_audio_files_sorted(self, scanner, temp_dir):
        """Test that audio files are returned sorted."""
        (temp_dir / "z.mp3").write_text("data")
        (temp_dir / "a.mp3").write_text("data")
        (temp_dir / "m.mp3").write_text("data")

        files = scanner._find_audio_files(temp_dir)

        # Check they're sorted
        assert files == sorted(files)


class TestMatchByFilePath:
    """Test _match_by_file_path method."""

    def test_match_by_file_path_found(self, scanner, db_service, temp_dir):
        """Test matching by exact file path."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("data")

        track_id = create_test_track(db_service, title="Song", file_path=str(file_path))
        track = db_service.get_track_by_id(track_id)

        result = scanner._match_by_file_path(file_path, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_by_file_path_not_found(self, scanner, db_service, temp_dir):
        """Test no match when file path differs."""
        file_path = temp_dir / "song.mp3"
        track_id = create_test_track(
            db_service, title="Song", file_path="/different/path.mp3"
        )
        track = db_service.get_track_by_id(track_id)

        result = scanner._match_by_file_path(file_path, [track])

        assert result is None

    def test_match_by_file_path_no_path_in_track(self, scanner, db_service, temp_dir):
        """Test no match when track has no file path."""
        file_path = temp_dir / "song.mp3"
        track_id = create_test_track(db_service, title="Song", file_path=None)
        track = db_service.get_track_by_id(track_id)

        result = scanner._match_by_file_path(file_path, [track])

        assert result is None


class TestMatchByISRC:
    """Test _match_by_isrc method."""

    def test_match_by_isrc_found(self, scanner, db_service):
        """Test matching by ISRC code."""
        track_id = create_test_track(db_service, title="Song", isrc="USABC1234567")
        track = db_service.get_track_by_id(track_id)

        metadata = {"isrc": "USABC1234567"}
        result = scanner._match_by_isrc(metadata, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_by_isrc_not_found(self, scanner, db_service):
        """Test no match when ISRC differs."""
        track_id = create_test_track(db_service, title="Song", isrc="USABC1234567")
        track = db_service.get_track_by_id(track_id)

        metadata = {"isrc": "DIFFERENT123"}
        result = scanner._match_by_isrc(metadata, [track])

        assert result is None

    def test_match_by_isrc_no_isrc_in_metadata(self, scanner, db_service):
        """Test no match when metadata has no ISRC."""
        track_id = create_test_track(db_service, title="Song", isrc="USABC1234567")
        track = db_service.get_track_by_id(track_id)

        metadata = {}
        result = scanner._match_by_isrc(metadata, [track])

        assert result is None

    def test_match_by_isrc_no_isrc_in_track(self, scanner, db_service):
        """Test no match when track has no ISRC."""
        track_id = create_test_track(db_service, title="Song", isrc=None)
        track = db_service.get_track_by_id(track_id)

        metadata = {"isrc": "USABC1234567"}
        result = scanner._match_by_isrc(metadata, [track])

        assert result is None


class TestMatchByMetadata:
    """Test _match_by_metadata method."""

    def test_match_by_metadata_exact(self, scanner, db_service):
        """Test exact metadata match."""
        track_id = create_test_track(
            db_service, title="Song Title", artist="Artist Name", album="Album Name"
        )
        track = db_service.get_track_by_id(track_id)

        metadata = {
            "title": "Song Title",
            "artist": "Artist Name",
            "album": "Album Name",
        }
        result = scanner._match_by_metadata(metadata, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_by_metadata_case_insensitive(self, scanner, db_service):
        """Test case-insensitive metadata match."""
        track_id = create_test_track(
            db_service, title="Song Title", artist="Artist Name"
        )
        track = db_service.get_track_by_id(track_id)

        metadata = {"title": "SONG TITLE", "artist": "ARTIST NAME"}
        result = scanner._match_by_metadata(metadata, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_by_metadata_no_album(self, scanner, db_service):
        """Test match without album."""
        track_id = create_test_track(db_service, title="Song", artist="Artist")
        track = db_service.get_track_by_id(track_id)

        metadata = {"title": "Song", "artist": "Artist"}
        result = scanner._match_by_metadata(metadata, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_by_metadata_fuzzy(self, scanner, db_service):
        """Test fuzzy metadata match (contains)."""
        track_id = create_test_track(
            db_service, title="The Great Song", artist="The Artist Name"
        )
        track = db_service.get_track_by_id(track_id)

        metadata = {"title": "Great Song", "artist": "Artist Name"}
        result = scanner._match_by_metadata(metadata, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_by_metadata_no_title(self, scanner, db_service):
        """Test no match when title missing."""
        track_id = create_test_track(db_service, title="Song", artist="Artist")
        track = db_service.get_track_by_id(track_id)

        metadata = {"artist": "Artist"}
        result = scanner._match_by_metadata(metadata, [track])

        assert result is None

    def test_match_by_metadata_no_artist(self, scanner, db_service):
        """Test no match when artist missing."""
        track_id = create_test_track(db_service, title="Song", artist="Artist")
        track = db_service.get_track_by_id(track_id)

        metadata = {"title": "Song"}
        result = scanner._match_by_metadata(metadata, [track])

        assert result is None


class TestMatchByFileHash:
    """Test _match_by_file_hash method."""

    def test_match_by_file_hash_found(self, scanner, db_service, temp_dir):
        """Test matching by file hash."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("unique content")

        # Compute hash
        file_hash = scanner._compute_file_hash(file_path)

        track_id = create_test_track(db_service, title="Song", file_hash=file_hash)
        track = db_service.get_track_by_id(track_id)

        result = scanner._match_by_file_hash(file_path, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_by_file_hash_not_found(self, scanner, db_service, temp_dir):
        """Test no match when hash differs."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("content")

        track_id = create_test_track(
            db_service, title="Song", file_hash="different_hash"
        )
        track = db_service.get_track_by_id(track_id)

        result = scanner._match_by_file_hash(file_path, [track])

        assert result is None

    def test_match_by_file_hash_no_hash_in_track(self, scanner, db_service, temp_dir):
        """Test no match when track has no hash."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("content")

        track_id = create_test_track(db_service, title="Song", file_hash=None)
        track = db_service.get_track_by_id(track_id)

        result = scanner._match_by_file_hash(file_path, [track])

        assert result is None


class TestExtractFileMetadata:
    """Test _extract_file_metadata method."""

    def test_extract_metadata_success(self, scanner, temp_dir):
        """Test successful metadata extraction."""
        file_path = temp_dir / "song.mp3"

        # Mock mutagen
        mock_audio = MagicMock()
        mock_audio.tags = {
            "title": ["Test Song"],
            "artist": ["Test Artist"],
            "album": ["Test Album"],
            "isrc": ["USABC1234567"],
        }
        mock_audio.info.length = 180.5

        with patch("tidal_cleanup.database.file_scanner_service.MutagenFile") as mock:
            mock.return_value = mock_audio
            metadata = scanner._extract_file_metadata(file_path)

        assert metadata is not None
        assert metadata["title"] == "Test Song"
        assert metadata["artist"] == "Test Artist"
        assert metadata["album"] == "Test Album"
        assert metadata["isrc"] == "USABC1234567"
        assert metadata["duration"] == 180.5

    def test_extract_metadata_no_audio(self, scanner, temp_dir):
        """Test when mutagen returns None."""
        file_path = temp_dir / "song.mp3"

        with patch("tidal_cleanup.database.file_scanner_service.MutagenFile") as mock:
            mock.return_value = None
            metadata = scanner._extract_file_metadata(file_path)

        assert metadata is None

    def test_extract_metadata_exception(self, scanner, temp_dir):
        """Test exception handling during metadata extraction."""
        file_path = temp_dir / "song.mp3"

        with patch("tidal_cleanup.database.file_scanner_service.MutagenFile") as mock:
            mock.side_effect = Exception("Read error")
            metadata = scanner._extract_file_metadata(file_path)

        assert metadata is None


class TestGetTagValue:
    """Test _get_tag_value method."""

    def test_get_tag_value_list(self, scanner):
        """Test getting tag value from list."""
        audio = Mock()
        audio.tags = {"artist": ["Artist Name", "Another"]}
        value = scanner._get_tag_value(audio, "artist")
        assert value == "Artist Name"

    def test_get_tag_value_string(self, scanner):
        """Test getting tag value that's a string."""
        audio = Mock()
        audio.tags = {"title": "Song Title"}
        value = scanner._get_tag_value(audio, "title")
        assert value == "Song Title"

    def test_get_tag_value_no_tags(self, scanner):
        """Test when audio has no tags."""
        audio = Mock(spec=[])  # No tags attribute
        value = scanner._get_tag_value(audio, "title")
        assert value is None

    def test_get_tag_value_tag_not_present(self, scanner):
        """Test when tag not present."""
        audio = Mock()
        audio.tags = {"artist": ["Artist"]}
        value = scanner._get_tag_value(audio, "title")
        assert value is None

    def test_get_tag_value_exception(self, scanner):
        """Test exception handling."""
        audio = Mock()
        # Create a mock that raises when accessed as string or list
        mock_value = Mock()
        mock_value.__getitem__ = Mock(side_effect=Exception("Error"))
        mock_value.__str__ = Mock(side_effect=Exception("Error"))
        audio.tags = {"title": mock_value}
        value = scanner._get_tag_value(audio, "title")
        assert value is None


class TestComputeFileHash:
    """Test _compute_file_hash method."""

    def test_compute_file_hash_success(self, scanner, temp_dir):
        """Test computing file hash."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("test content")

        hash_value = scanner._compute_file_hash(file_path)

        assert hash_value is not None
        assert len(hash_value) == 64  # SHA256 hex digest length

    def test_compute_file_hash_same_content(self, scanner, temp_dir):
        """Test that same content produces same hash."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        content = "identical content"

        file1.write_text(content)
        file2.write_text(content)

        hash1 = scanner._compute_file_hash(file1)
        hash2 = scanner._compute_file_hash(file2)

        assert hash1 == hash2

    def test_compute_file_hash_different_content(self, scanner, temp_dir):
        """Test that different content produces different hashes."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        file1.write_text("content1")
        file2.write_text("content2")

        hash1 = scanner._compute_file_hash(file1)
        hash2 = scanner._compute_file_hash(file2)

        assert hash1 != hash2

    def test_compute_file_hash_nonexistent(self, scanner, temp_dir):
        """Test computing hash for nonexistent file."""
        file_path = temp_dir / "nonexistent.txt"
        hash_value = scanner._compute_file_hash(file_path)
        assert hash_value is None


class TestUpdateTrackFileInfo:
    """Test _update_track_file_info method."""

    def test_update_track_file_info_success(self, scanner, db_service, temp_dir):
        """Test updating track with file info."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("audio content")

        track_id = create_test_track(db_service, title="Song")
        track = db_service.get_track_by_id(track_id)

        scanner._update_track_file_info(track, file_path)

        # Verify track was updated
        updated_track = db_service.get_track_by_id(track_id)
        assert updated_track.file_path == str(file_path)
        assert updated_track.file_hash is not None

    def test_update_track_file_info_exception(self, scanner, db_service, temp_dir):
        """Test exception handling during update."""
        file_path = temp_dir / "song.mp3"
        track_id = create_test_track(db_service, title="Song")
        track = db_service.get_track_by_id(track_id)

        with patch.object(db_service, "update_track", side_effect=Exception("Error")):
            # Should not raise exception
            scanner._update_track_file_info(track, file_path)


class TestFindMissingFiles:
    """Test find_missing_files method."""

    def test_find_missing_files_all_exist(self, scanner, db_service, temp_dir):
        """Test when all files exist."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("data")

        create_test_track(
            db_service, tidal_id="exists1", title="Song", file_path=str(file_path)
        )

        missing = scanner.find_missing_files()

        assert len(missing) == 0

    def test_find_missing_files_some_missing(self, scanner, db_service, temp_dir):
        """Test finding missing files."""
        file1 = temp_dir / "exists.mp3"
        file1.write_text("data")

        create_test_track(
            db_service, tidal_id="exists2", title="Exists", file_path=str(file1)
        )
        create_test_track(
            db_service,
            tidal_id="missing1",
            title="Missing",
            file_path=str(temp_dir / "missing.mp3"),
        )

        missing = scanner.find_missing_files()

        assert len(missing) == 1
        assert missing[0].title == "Missing"

    def test_find_missing_files_no_path(self, scanner, db_service):
        """Test tracks with no file path are considered missing."""
        create_test_track(
            db_service, tidal_id="nopath1", title="No Path", file_path=None
        )

        missing = scanner.find_missing_files()

        assert len(missing) == 1
        assert missing[0].title == "No Path"


class TestFindOrphanedFiles:
    """Test find_orphaned_files method."""

    def test_find_orphaned_files_none(self, scanner, db_service, temp_dir):
        """Test when no orphaned files."""
        file1 = temp_dir / "song1.mp3"
        file1.write_text("data")

        create_test_track(db_service, title="Song", file_path=str(file1))

        orphaned = scanner.find_orphaned_files(temp_dir)

        assert len(orphaned) == 0

    def test_find_orphaned_files_some_orphaned(self, scanner, db_service, temp_dir):
        """Test finding orphaned files."""
        file1 = temp_dir / "known.mp3"
        file2 = temp_dir / "orphan.mp3"
        file1.write_text("data")
        file2.write_text("data")

        create_test_track(db_service, title="Known", file_path=str(file1))

        orphaned = scanner.find_orphaned_files(temp_dir)

        assert len(orphaned) == 1
        assert orphaned[0].name == "orphan.mp3"


class TestUpdateFileHashes:
    """Test update_file_hashes method."""

    def test_update_file_hashes_all_tracks(self, scanner, db_service, temp_dir):
        """Test updating hashes for all tracks."""
        file1 = temp_dir / "song1.mp3"
        file2 = temp_dir / "song2.mp3"
        file1.write_text("content1")
        file2.write_text("content2")

        create_test_track(
            db_service, tidal_id="hash1", title="Song1", file_path=str(file1)
        )
        create_test_track(
            db_service, tidal_id="hash2", title="Song2", file_path=str(file2)
        )

        updated = scanner.update_file_hashes()

        assert updated == 2

    def test_update_file_hashes_skip_missing(self, scanner, db_service, temp_dir):
        """Test skipping tracks with missing files."""
        file1 = temp_dir / "exists.mp3"
        file1.write_text("content")

        create_test_track(
            db_service, tidal_id="hash3", title="Exists", file_path=str(file1)
        )
        create_test_track(
            db_service,
            tidal_id="hash4",
            title="Missing",
            file_path=str(temp_dir / "missing.mp3"),
        )

        updated = scanner.update_file_hashes()

        assert updated == 1

    def test_update_file_hashes_directory_filter(self, scanner, db_service, temp_dir):
        """Test updating hashes for specific directory."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()

        file1 = temp_dir / "song1.mp3"
        file2 = subdir / "song2.mp3"
        file1.write_text("content1")
        file2.write_text("content2")

        create_test_track(
            db_service, tidal_id="hash5", title="Song1", file_path=str(file1)
        )
        create_test_track(
            db_service, tidal_id="hash6", title="Song2", file_path=str(file2)
        )

        updated = scanner.update_file_hashes(directory=subdir)

        assert updated == 1

    def test_update_file_hashes_skip_unchanged(self, scanner, db_service, temp_dir):
        """Test skipping tracks where hash hasn't changed."""
        file1 = temp_dir / "song.mp3"
        file1.write_text("content")

        # Create track with correct hash
        file_hash = scanner._compute_file_hash(file1)
        create_test_track(
            db_service,
            tidal_id="hash7",
            title="Song",
            file_path=str(file1),
            file_hash=file_hash,
        )

        updated = scanner.update_file_hashes()

        assert updated == 0


class TestVerifyFileIntegrity:
    """Test verify_file_integrity method."""

    def test_verify_file_integrity_all_valid(self, scanner, db_service, temp_dir):
        """Test when all files are valid."""
        file1 = temp_dir / "song.mp3"
        file1.write_text("content")

        file_hash = scanner._compute_file_hash(file1)
        create_test_track(
            db_service, title="Song", file_path=str(file1), file_hash=file_hash
        )

        result = scanner.verify_file_integrity()

        assert len(result["valid"]) == 1
        assert len(result["missing"]) == 0
        assert len(result["modified"]) == 0
        assert len(result["no_hash"]) == 0

    def test_verify_file_integrity_missing(self, scanner, db_service, temp_dir):
        """Test detecting missing files."""
        create_test_track(
            db_service,
            title="Missing",
            file_path=str(temp_dir / "missing.mp3"),
            file_hash="hash",
        )

        result = scanner.verify_file_integrity()

        assert len(result["missing"]) == 1
        assert result["missing"][0].title == "Missing"

    def test_verify_file_integrity_modified(self, scanner, db_service, temp_dir):
        """Test detecting modified files."""
        file1 = temp_dir / "song.mp3"
        file1.write_text("original content")

        old_hash = scanner._compute_file_hash(file1)
        create_test_track(
            db_service, title="Song", file_path=str(file1), file_hash=old_hash
        )

        # Modify file
        file1.write_text("modified content")

        result = scanner.verify_file_integrity()

        assert len(result["modified"]) == 1
        assert result["modified"][0].title == "Song"

    def test_verify_file_integrity_no_hash(self, scanner, db_service, temp_dir):
        """Test detecting files with no hash."""
        file1 = temp_dir / "song.mp3"
        file1.write_text("content")

        create_test_track(
            db_service, title="No Hash", file_path=str(file1), file_hash=None
        )

        result = scanner.verify_file_integrity()

        assert len(result["no_hash"]) == 1
        assert result["no_hash"][0].title == "No Hash"

    def test_verify_file_integrity_no_path(self, scanner, db_service):
        """Test tracks with no file path."""
        create_test_track(db_service, title="No Path", file_path=None)

        result = scanner.verify_file_integrity()

        assert len(result["no_hash"]) == 1
        assert result["no_hash"][0].title == "No Path"


class TestMatchFileToTrack:
    """Test _match_file_to_track integration."""

    def test_match_file_to_track_by_path(self, scanner, db_service, temp_dir):
        """Test matching prioritizes file path."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("data")

        track_id = create_test_track(db_service, title="Song", file_path=str(file_path))
        track = db_service.get_track_by_id(track_id)

        result = scanner._match_file_to_track(file_path, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_file_to_track_no_metadata(self, scanner, db_service, temp_dir):
        """Test when metadata extraction fails."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("data")

        track_id = create_test_track(db_service, title="Song")
        track = db_service.get_track_by_id(track_id)

        with patch.object(scanner, "_extract_file_metadata", return_value=None):
            result = scanner._match_file_to_track(file_path, [track])

        assert result is None

    def test_match_file_to_track_by_isrc(self, scanner, db_service, temp_dir):
        """Test matching by ISRC when path doesn't match."""
        file_path = temp_dir / "song.mp3"

        track_id = create_test_track(db_service, title="Song", isrc="USABC1234567")
        track = db_service.get_track_by_id(track_id)

        mock_metadata = {"isrc": "USABC1234567", "title": "Song", "artist": "Artist"}

        with patch.object(
            scanner, "_extract_file_metadata", return_value=mock_metadata
        ):
            result = scanner._match_file_to_track(file_path, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_file_to_track_by_metadata(self, scanner, db_service, temp_dir):
        """Test matching by metadata when ISRC doesn't match."""
        file_path = temp_dir / "song.mp3"

        track_id = create_test_track(
            db_service, tidal_id="meta1", title="Song Title", artist="Artist Name"
        )
        track = db_service.get_track_by_id(track_id)

        mock_metadata = {
            "isrc": None,
            "title": "Song Title",
            "artist": "Artist Name",
        }

        with patch.object(
            scanner, "_extract_file_metadata", return_value=mock_metadata
        ):
            result = scanner._match_file_to_track(file_path, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_file_to_track_by_hash(self, scanner, db_service, temp_dir):
        """Test matching by file hash when metadata doesn't match."""
        file_path = temp_dir / "song.mp3"
        file_path.write_text("unique content")

        file_hash = scanner._compute_file_hash(file_path)
        track_id = create_test_track(
            db_service,
            tidal_id="hash_match",
            title="Different Title",
            artist="Different Artist",
            file_hash=file_hash,
        )
        track = db_service.get_track_by_id(track_id)

        mock_metadata = {"isrc": None, "title": "Wrong", "artist": "Wrong"}

        with patch.object(
            scanner, "_extract_file_metadata", return_value=mock_metadata
        ):
            result = scanner._match_file_to_track(file_path, [track])

        assert result is not None
        assert result.id == track_id

    def test_match_file_to_track_no_match(self, scanner, db_service, temp_dir):
        """Test when no matching strategy succeeds."""
        file_path = temp_dir / "unknown.mp3"
        file_path.write_text("content")

        track_id = create_test_track(
            db_service,
            tidal_id="nomatch",
            title="Different",
            artist="Different",
            file_path="/other/path.mp3",
        )
        track = db_service.get_track_by_id(track_id)

        mock_metadata = {"isrc": None, "title": "Other", "artist": "Other"}

        with patch.object(
            scanner, "_extract_file_metadata", return_value=mock_metadata
        ), patch.object(scanner, "_compute_file_hash", return_value=None):
            result = scanner._match_file_to_track(file_path, [track])

        assert result is None


class TestUpdateFileHashesNoPath:
    """Test update_file_hashes with tracks without file paths."""

    def test_update_file_hashes_skip_no_path(self, scanner, db_service):
        """Test skipping tracks with no file path."""
        create_test_track(db_service, tidal_id="nopath_hash", title="No Path")

        updated = scanner.update_file_hashes()

        assert updated == 0
