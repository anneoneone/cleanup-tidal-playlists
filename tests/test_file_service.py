"""Tests for refactored FileService methods."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tidal_cleanup.legacy.directory_diff import FileIdentity
from tidal_cleanup.legacy.file_service import FileService
from tidal_cleanup.models.models import ConversionJob


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with (
        tempfile.TemporaryDirectory() as source_dir,
        tempfile.TemporaryDirectory() as target_dir,
    ):
        yield Path(source_dir), Path(target_dir)


@pytest.fixture
def file_service():
    """Create a FileService instance."""
    return FileService()


class TestConvertMissingFiles:
    """Tests for _convert_missing_files method."""

    def test_convert_single_file(self, file_service, temp_dirs):
        """Test converting a single missing file."""
        source_dir, target_dir = temp_dirs

        # Create source file
        source_file = source_dir / "track1.m4a"
        source_file.write_text("audio data")

        # Create file identity
        file_stems = {"track1"}
        source_identities = {"track1": FileIdentity(key="track1", path=source_file)}

        # Mock the convert_audio method
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_job = ConversionJob(
                source_path=source_file,
                target_path=target_dir / "track1.mp3",
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )
            mock_convert.return_value = mock_job

            # Execute
            jobs = file_service._convert_missing_files(
                source_dir=source_dir,
                target_dir=target_dir,
                file_stems=file_stems,
                source_identities=source_identities,
                target_format=".mp3",
                quality="2",
            )

            # Assert
            assert len(jobs) == 1
            assert jobs[0].status == "completed"
            assert jobs[0].source_path == source_file
            assert jobs[0].target_path == target_dir / "track1.mp3"
            mock_convert.assert_called_once()

    def test_convert_multiple_files(self, file_service, temp_dirs):
        """Test converting multiple missing files."""
        source_dir, target_dir = temp_dirs

        # Create source files
        files = ["track1.m4a", "track2.m4a", "track3.mp4"]
        for filename in files:
            (source_dir / filename).write_text("audio data")

        # Create file identities
        file_stems = {Path(f).stem for f in files}
        source_identities = {
            Path(f).stem: FileIdentity(key=Path(f).stem, path=source_dir / f)
            for f in files
        }

        # Mock the convert_audio method
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=source_dir / "dummy.m4a",
                target_path=target_dir / "dummy.mp3",
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            # Execute
            jobs = file_service._convert_missing_files(
                source_dir=source_dir,
                target_dir=target_dir,
                file_stems=file_stems,
                source_identities=source_identities,
                target_format=".mp3",
                quality="2",
            )

            # Assert
            assert len(jobs) == 3
            assert mock_convert.call_count == 3

    def test_convert_with_subdirectories(self, file_service, temp_dirs):
        """Test converting files in subdirectories."""
        source_dir, target_dir = temp_dirs

        # Create subdirectory and file
        subdir = source_dir / "artist" / "album"
        subdir.mkdir(parents=True)
        source_file = subdir / "track1.m4a"
        source_file.write_text("audio data")

        # Create file identity
        file_stems = {"track1"}
        source_identities = {"track1": FileIdentity(key="track1", path=source_file)}

        # Mock the convert_audio method
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_job = ConversionJob(
                source_path=source_file,
                target_path=target_dir / "artist" / "album" / "track1.mp3",
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )
            mock_convert.return_value = mock_job

            # Execute
            jobs = file_service._convert_missing_files(
                source_dir=source_dir,
                target_dir=target_dir,
                file_stems=file_stems,
                source_identities=source_identities,
                target_format=".mp3",
                quality="2",
            )

            # Assert
            assert len(jobs) == 1
            # Verify the relative path structure is preserved
            call_args = mock_convert.call_args
            target_path = call_args[0][1]  # Second positional argument
            assert target_path == target_dir / "artist" / "album" / "track1.mp3"

    def test_convert_empty_file_stems(self, file_service, temp_dirs):
        """Test with no files to convert."""
        source_dir, target_dir = temp_dirs

        # Execute with empty sets
        jobs = file_service._convert_missing_files(
            source_dir=source_dir,
            target_dir=target_dir,
            file_stems=set(),
            source_identities={},
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 0


class TestDeleteOrphanedFiles:
    """Tests for _delete_orphaned_files method."""

    def test_delete_single_file(self, file_service, temp_dirs):
        """Test deleting a single orphaned file."""
        source_dir, target_dir = temp_dirs

        # Create target file
        target_file = target_dir / "orphan.mp3"
        target_file.write_text("old audio data")

        # Create file identity
        file_stems = {"orphan"}
        target_identities = {"orphan": FileIdentity(key="orphan", path=target_file)}

        # Execute
        jobs = file_service._delete_orphaned_files(
            file_stems=file_stems,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 1
        assert jobs[0].status == "deleted"
        assert jobs[0].target_path == target_file
        assert jobs[0].source_path == Path("")
        assert not target_file.exists()

    def test_delete_multiple_files(self, file_service, temp_dirs):
        """Test deleting multiple orphaned files."""
        source_dir, target_dir = temp_dirs

        # Create target files
        files = ["orphan1.mp3", "orphan2.mp3", "orphan3.mp3"]
        for filename in files:
            (target_dir / filename).write_text("old audio data")

        # Create file identities
        file_stems = {Path(f).stem for f in files}
        target_identities = {
            Path(f).stem: FileIdentity(key=Path(f).stem, path=target_dir / f)
            for f in files
        }

        # Execute
        jobs = file_service._delete_orphaned_files(
            file_stems=file_stems,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 3
        for job in jobs:
            assert job.status == "deleted"
            assert not job.target_path.exists()

    def test_delete_file_in_subdirectory(self, file_service, temp_dirs):
        """Test deleting orphaned file in subdirectory."""
        source_dir, target_dir = temp_dirs

        # Create subdirectory and file
        subdir = target_dir / "artist" / "album"
        subdir.mkdir(parents=True)
        target_file = subdir / "orphan.mp3"
        target_file.write_text("old audio data")

        # Create file identity
        file_stems = {"orphan"}
        target_identities = {"orphan": FileIdentity(key="orphan", path=target_file)}

        # Execute
        jobs = file_service._delete_orphaned_files(
            file_stems=file_stems,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 1
        assert jobs[0].status == "deleted"
        assert not target_file.exists()

    def test_delete_nonexistent_file(self, file_service, temp_dirs, caplog):
        """Test attempting to delete a file that doesn't exist."""
        source_dir, target_dir = temp_dirs

        # Create file identity for non-existent file
        nonexistent_file = target_dir / "nonexistent.mp3"
        file_stems = {"nonexistent"}
        target_identities = {
            "nonexistent": FileIdentity(key="nonexistent", path=nonexistent_file)
        }

        # Execute
        jobs = file_service._delete_orphaned_files(
            file_stems=file_stems,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert - should handle gracefully and not create a job
        assert len(jobs) == 0
        assert "Failed to delete" in caplog.text

    def test_delete_empty_file_stems(self, file_service, temp_dirs):
        """Test with no files to delete."""
        source_dir, target_dir = temp_dirs

        # Execute with empty sets
        jobs = file_service._delete_orphaned_files(
            file_stems=set(),
            target_identities={},
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 0


class TestTrackSkippedFiles:
    """Tests for _track_skipped_files method."""

    def test_track_single_skipped_file(self, file_service, temp_dirs):
        """Test tracking a single skipped file."""
        source_dir, target_dir = temp_dirs

        # Create files
        source_file = source_dir / "track1.m4a"
        target_file = target_dir / "track1.mp3"
        source_file.write_text("audio data")
        target_file.write_text("converted audio data")

        # Create file identities
        file_stems = {"track1"}
        source_identities = {"track1": FileIdentity(key="track1", path=source_file)}
        target_identities = {"track1": FileIdentity(key="track1", path=target_file)}

        # Execute
        jobs = file_service._track_skipped_files(
            file_stems=file_stems,
            source_identities=source_identities,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 1
        assert jobs[0].status == "completed"
        assert jobs[0].was_skipped is True
        assert jobs[0].source_path == source_file
        assert jobs[0].target_path == target_file
        assert jobs[0].source_format == ".m4a"
        assert jobs[0].target_format == ".mp3"

    def test_track_multiple_skipped_files(self, file_service, temp_dirs):
        """Test tracking multiple skipped files."""
        source_dir, target_dir = temp_dirs

        # Create multiple file pairs
        tracks = ["track1", "track2", "track3"]
        source_identities = {}
        target_identities = {}

        for track in tracks:
            source_file = source_dir / f"{track}.m4a"
            target_file = target_dir / f"{track}.mp3"
            source_file.write_text("audio data")
            target_file.write_text("converted audio data")

            source_identities[track] = FileIdentity(key=track, path=source_file)
            target_identities[track] = FileIdentity(key=track, path=target_file)

        # Execute
        jobs = file_service._track_skipped_files(
            file_stems=set(tracks),
            source_identities=source_identities,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 3
        for job in jobs:
            assert job.status == "completed"
            assert job.was_skipped is True

    def test_track_skipped_with_different_formats(self, file_service, temp_dirs):
        """Test tracking skipped files with different source formats."""
        source_dir, target_dir = temp_dirs

        # Create files with different formats
        tracks = [
            ("track1", ".m4a"),
            ("track2", ".mp4"),
        ]
        source_identities = {}
        target_identities = {}

        for track, ext in tracks:
            source_file = source_dir / f"{track}{ext}"
            target_file = target_dir / f"{track}.mp3"
            source_file.write_text("audio data")
            target_file.write_text("converted audio data")

            source_identities[track] = FileIdentity(key=track, path=source_file)
            target_identities[track] = FileIdentity(key=track, path=target_file)

        # Execute
        jobs = file_service._track_skipped_files(
            file_stems={track for track, _ in tracks},
            source_identities=source_identities,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 2
        assert jobs[0].source_format in [".m4a", ".mp4"]
        assert jobs[1].source_format in [".m4a", ".mp4"]
        for job in jobs:
            assert job.target_format == ".mp3"
            assert job.was_skipped is True

    def test_track_skipped_in_subdirectories(self, file_service, temp_dirs):
        """Test tracking skipped files in subdirectories."""
        source_dir, target_dir = temp_dirs

        # Create subdirectories
        source_subdir = source_dir / "artist" / "album"
        target_subdir = target_dir / "artist" / "album"
        source_subdir.mkdir(parents=True)
        target_subdir.mkdir(parents=True)

        # Create files
        source_file = source_subdir / "track1.m4a"
        target_file = target_subdir / "track1.mp3"
        source_file.write_text("audio data")
        target_file.write_text("converted audio data")

        # Create file identities
        file_stems = {"track1"}
        source_identities = {"track1": FileIdentity(key="track1", path=source_file)}
        target_identities = {"track1": FileIdentity(key="track1", path=target_file)}

        # Execute
        jobs = file_service._track_skipped_files(
            file_stems=file_stems,
            source_identities=source_identities,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 1
        assert jobs[0].was_skipped is True
        assert "artist" in str(jobs[0].source_path)
        assert "album" in str(jobs[0].source_path)

    def test_track_empty_file_stems(self, file_service, temp_dirs):
        """Test with no files to track."""
        source_dir, target_dir = temp_dirs

        # Execute with empty sets
        jobs = file_service._track_skipped_files(
            file_stems=set(),
            source_identities={},
            target_identities={},
            target_format=".mp3",
            quality="2",
        )

        # Assert
        assert len(jobs) == 0


class TestIntegrationScenarios:
    """Integration tests combining multiple methods."""

    def test_complete_playlist_processing_scenario(self, file_service, temp_dirs):
        """Test a realistic scenario with files to convert, delete, and skip."""
        source_dir, target_dir = temp_dirs

        # Create scenario:
        # - track1: exists in both (skip)
        # - track2: only in source (convert)
        # - track3: only in target (delete)

        # Files that exist in both
        (source_dir / "track1.m4a").write_text("audio")
        (target_dir / "track1.mp3").write_text("converted")

        # File only in source
        (source_dir / "track2.m4a").write_text("audio")

        # File only in target
        (target_dir / "track3.mp3").write_text("old converted")

        # Create identities
        source_identities = {
            "track1": FileIdentity(key="track1", path=source_dir / "track1.m4a"),
            "track2": FileIdentity(key="track2", path=source_dir / "track2.m4a"),
        }
        target_identities = {
            "track1": FileIdentity(key="track1", path=target_dir / "track1.mp3"),
            "track3": FileIdentity(key="track3", path=target_dir / "track3.mp3"),
        }

        all_jobs = []

        # Convert missing files
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=source_dir / "track2.m4a",
                target_path=target_dir / "track2.mp3",
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            convert_jobs = file_service._convert_missing_files(
                source_dir=source_dir,
                target_dir=target_dir,
                file_stems={"track2"},
                source_identities=source_identities,
                target_format=".mp3",
                quality="2",
            )
            all_jobs.extend(convert_jobs)

        # Delete orphaned files
        delete_jobs = file_service._delete_orphaned_files(
            file_stems={"track3"},
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )
        all_jobs.extend(delete_jobs)

        # Track skipped files
        skip_jobs = file_service._track_skipped_files(
            file_stems={"track1"},
            source_identities=source_identities,
            target_identities=target_identities,
            target_format=".mp3",
            quality="2",
        )
        all_jobs.extend(skip_jobs)

        # Assert
        assert len(all_jobs) == 3
        converted = [
            j for j in all_jobs if j.status == "completed" and not j.was_skipped
        ]
        deleted = [j for j in all_jobs if j.status == "deleted"]
        skipped = [j for j in all_jobs if j.was_skipped]

        assert len(converted) == 1
        assert len(deleted) == 1
        assert len(skipped) == 1

        assert not (target_dir / "track3.mp3").exists()


class TestCreateTrackFromFile:
    """Tests for create_track_from_file method."""

    def test_create_track_with_full_metadata(self, file_service):
        """Test creating track from FileInfo with complete metadata."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/song.mp3")
        file_info = FileInfo(
            path=file_path,
            name="song.mp3",
            size=5000000,
            format=".mp3",
            duration=180,
            bitrate=320000,
            sample_rate=44100,
            metadata={
                "title": ["Awesome Song"],
                "artist": ["Great Artist"],
                "album": ["Best Album"],
                "genre": ["Rock"],
            },
        )

        track = file_service.create_track_from_file(file_info)

        assert track is not None
        assert track.title == "Awesome Song"
        assert track.artist == "Great Artist"
        assert track.album == "Best Album"
        assert track.genre == "Rock"
        assert track.duration == 180
        assert track.file_path == file_path
        assert track.file_size == 5000000
        assert track.file_format == ".mp3"

    def test_create_track_with_minimal_metadata(self, file_service):
        """Test creating track with only required metadata fields."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/minimal.mp3")
        file_info = FileInfo(
            path=file_path,
            name="minimal.mp3",
            size=3000000,
            format=".mp3",
            duration=120,
            metadata={
                "title": ["Minimal Song"],
                "artist": ["Solo Artist"],
            },
        )

        track = file_service.create_track_from_file(file_info)

        assert track is not None
        assert track.title == "Minimal Song"
        assert track.artist == "Solo Artist"
        assert track.album is None
        assert track.genre is None
        assert track.duration == 120

    def test_create_track_with_no_metadata(self, file_service):
        """Test that None is returned when FileInfo has no metadata."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/no_metadata.mp3")
        file_info = FileInfo(
            path=file_path,
            name="no_metadata.mp3",
            size=2000000,
            format=".mp3",
            duration=90,
            metadata=None,
        )

        track = file_service.create_track_from_file(file_info)

        assert track is None

    def test_create_track_with_empty_metadata(self, file_service):
        """Test that None is returned when FileInfo has empty metadata dict."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/empty_metadata.mp3")
        file_info = FileInfo(
            path=file_path,
            name="empty_metadata.mp3",
            size=2000000,
            format=".mp3",
            duration=90,
            metadata={},
        )

        track = file_service.create_track_from_file(file_info)

        # Empty dict is falsy in Python, so it returns None
        assert track is None

    def test_create_track_uses_stem_as_fallback_title(self, file_service):
        """Test that file stem is used when title is missing."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/track_name.mp3")
        file_info = FileInfo(
            path=file_path,
            name="track_name.mp3",
            size=2000000,
            format=".mp3",
            duration=150,
            metadata={
                "artist": ["Some Artist"],
            },
        )

        track = file_service.create_track_from_file(file_info)

        assert track is not None
        assert track.title == "track_name"
        assert track.artist == "Some Artist"

    def test_create_track_uses_unknown_artist_as_fallback(self, file_service):
        """Test that 'Unknown Artist' is used when artist is missing."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/orphan.mp3")
        file_info = FileInfo(
            path=file_path,
            name="orphan.mp3",
            size=2000000,
            format=".mp3",
            duration=150,
            metadata={
                "title": ["Orphan Track"],
            },
        )

        track = file_service.create_track_from_file(file_info)

        assert track is not None
        assert track.title == "Orphan Track"
        assert track.artist == "Unknown Artist"

    def test_create_track_with_multiple_artists(self, file_service):
        """Test handling metadata with multiple values (uses first)."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/collab.mp3")
        file_info = FileInfo(
            path=file_path,
            name="collab.mp3",
            size=4000000,
            format=".mp3",
            duration=200,
            metadata={
                "title": ["Collaboration"],
                "artist": ["Artist One", "Artist Two", "Artist Three"],
                "album": ["Collab Album"],
            },
        )

        track = file_service.create_track_from_file(file_info)

        assert track is not None
        assert track.title == "Collaboration"
        assert track.artist == "Artist One"  # Uses first artist
        assert track.album == "Collab Album"

    def test_create_track_with_none_values_in_metadata(self, file_service):
        """Test handling metadata with None values."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/partial.mp3")
        file_info = FileInfo(
            path=file_path,
            name="partial.mp3",
            size=3000000,
            format=".mp3",
            duration=160,
            metadata={
                "title": ["Good Title"],
                "artist": ["Good Artist"],
                "album": [None],
                "genre": [None],
            },
        )

        track = file_service.create_track_from_file(file_info)

        assert track is not None
        assert track.title == "Good Title"
        assert track.artist == "Good Artist"
        assert track.album is None
        assert track.genre is None

    def test_create_track_preserves_file_info(self, file_service):
        """Test that file information is correctly preserved."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/music/library/artist/album/track.flac")
        file_info = FileInfo(
            path=file_path,
            name="track.flac",
            size=25000000,
            format=".flac",
            duration=300,
            bitrate=1411000,
            sample_rate=44100,
            metadata={
                "title": ["Long Track"],
                "artist": ["Classical Artist"],
            },
        )

        track = file_service.create_track_from_file(file_info)

        assert track is not None
        assert track.file_path == file_path
        assert track.file_size == 25000000
        assert track.file_format == ".flac"
        assert track.duration == 300

    def test_create_track_handles_exception(self, file_service, caplog):
        """Test that exceptions during track creation are handled gracefully."""
        from tidal_cleanup.models.models import FileInfo

        file_path = Path("/fake/path/bad.mp3")

        file_info = FileInfo(
            path=file_path,
            name="bad.mp3",
            size=1000,
            format=".mp3",
            metadata={
                "title": ["Good Title"],
                "artist": ["Artist"],
            },
        )

        # Mock the Track constructor to raise an exception
        with patch("tidal_cleanup.legacy.file_service.Track") as mock_track:
            mock_track.side_effect = ValueError("Simulated track creation error")

            track = file_service.create_track_from_file(file_info)

            assert track is None
            assert "Failed to create Track" in caplog.text

    def test_create_track_with_different_file_formats(self, file_service):
        """Test creating tracks from different audio formats."""
        from tidal_cleanup.models.models import FileInfo

        formats = [".mp3", ".flac", ".m4a", ".wav", ".aac"]

        for fmt in formats:
            file_path = Path(f"/fake/path/track{fmt}")
            file_info = FileInfo(
                path=file_path,
                name=f"track{fmt}",
                size=5000000,
                format=fmt,
                duration=180,
                metadata={
                    "title": [f"Track {fmt}"],
                    "artist": ["Test Artist"],
                },
            )

            track = file_service.create_track_from_file(file_info)

            assert track is not None
            assert track.file_format == fmt
            assert track.title == f"Track {fmt}"


class TestGetTracksWithMetadata:
    """Tests for get_tracks_with_metadata method."""

    def test_get_tracks_from_empty_directory(self, file_service, temp_dirs):
        """Test getting tracks from empty directory returns empty list."""
        source_dir, _ = temp_dirs

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert isinstance(tracks, list)
        assert len(tracks) == 0

    def test_get_tracks_with_metadata_returns_list(self, file_service, temp_dirs):
        """Test that get_tracks_with_metadata returns a list."""
        source_dir, _ = temp_dirs

        # Create a simple audio file
        audio_file = source_dir / "track.mp3"
        audio_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert isinstance(tracks, list)

    def test_get_tracks_creates_track_objects(self, file_service, temp_dirs):
        """Test that Track objects are created for files in directory."""
        from tidal_cleanup.models.models import Track

        source_dir, _ = temp_dirs

        # Create audio files
        (source_dir / "track1.mp3").write_text("audio data")
        (source_dir / "track2.flac").write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 2
        assert all(isinstance(track, Track) for track in tracks)

    def test_get_tracks_with_filename_parsing(self, file_service, temp_dirs):
        """Test parsing track info from filename format 'artist - title'."""
        source_dir, _ = temp_dirs

        # Create file with artist - title format
        audio_file = source_dir / "The Beatles - Hey Jude.mp3"
        audio_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.artist == "The Beatles"
        assert track.title == "Hey Jude"

    def test_get_tracks_without_separator_uses_unknown_artist(
        self, file_service, temp_dirs
    ):
        """Test files without ' - ' separator use 'Unknown Artist'."""
        source_dir, _ = temp_dirs

        # Create file without artist - title format
        audio_file = source_dir / "Just A Title.mp3"
        audio_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.artist == "Unknown Artist"
        assert track.title == "Just A Title"

    def test_get_tracks_with_multiple_separators(self, file_service, temp_dirs):
        """Test parsing filename with multiple ' - ' separators."""
        source_dir, _ = temp_dirs

        # Create file with multiple separators
        audio_file = source_dir / "Artist Name - Song - Remix.mp3"
        audio_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.artist == "Artist Name"
        # Title should be everything after first ' - '
        assert track.title == "Song - Remix"

    def test_get_tracks_with_nested_directories(self, file_service, temp_dirs):
        """Test getting tracks from nested directory structure."""
        source_dir, _ = temp_dirs

        # Create nested structure
        artist_dir = source_dir / "Artist"
        album_dir = artist_dir / "Album"
        album_dir.mkdir(parents=True)

        (album_dir / "track1.mp3").write_text("audio data")
        (album_dir / "track2.mp3").write_text("audio data")
        (artist_dir / "single.mp3").write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        # Should find all 3 tracks recursively
        assert len(tracks) == 3

    def test_get_tracks_with_various_formats(self, file_service, temp_dirs):
        """Test getting tracks with different audio formats."""
        source_dir, _ = temp_dirs

        formats = [".mp3", ".flac", ".wav", ".aac", ".m4a", ".mp4"]
        for fmt in formats:
            (source_dir / f"track{fmt}").write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == len(formats)
        track_formats = [track.file_format for track in tracks]
        assert set(track_formats) == set(formats)

    def test_get_tracks_ignores_non_audio_files(self, file_service, temp_dirs):
        """Test that non-audio files are ignored."""
        source_dir, _ = temp_dirs

        # Create audio and non-audio files
        (source_dir / "track.mp3").write_text("audio data")
        (source_dir / "readme.txt").write_text("text data")
        (source_dir / "image.jpg").write_bytes(b"image data")
        (source_dir / "data.json").write_text('{"key": "value"}')

        tracks = file_service.get_tracks_with_metadata(source_dir)

        # Should only find the audio file
        assert len(tracks) == 1
        assert tracks[0].file_path.name == "track.mp3"

    def test_get_tracks_with_special_characters_in_filename(
        self, file_service, temp_dirs
    ):
        """Test handling filenames with special characters."""
        source_dir, _ = temp_dirs

        # Create files with special characters
        filenames = [
            "Artist & Band - Song (2024).mp3",
            "Café del Mar - Sunset Mix.mp3",
            "Artist - Song [Remix].mp3",
        ]

        for filename in filenames:
            (source_dir / filename).write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 3
        # Verify titles were parsed correctly
        titles = [track.title for track in tracks]
        assert "Song (2024)" in titles
        assert "Sunset Mix" in titles
        assert "Song [Remix]" in titles

    def test_get_tracks_sets_file_info_attributes(self, file_service, temp_dirs):
        """Test that file information attributes are set on Track objects."""
        source_dir, _ = temp_dirs

        audio_file = source_dir / "Artist - Track.mp3"
        audio_file.write_text("audio data content")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.file_path == audio_file
        assert track.file_size > 0
        assert track.file_format == ".mp3"

    def test_get_tracks_handles_whitespace_in_artist_title(
        self, file_service, temp_dirs
    ):
        """Test that extra whitespace around artist and title is stripped."""
        source_dir, _ = temp_dirs

        # Create file with extra whitespace
        audio_file = source_dir / "  Artist Name  -  Song Title  .mp3"
        audio_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.artist == "Artist Name"
        assert track.title == "Song Title"

    def test_get_tracks_sets_album_to_none_for_parsed_filenames(
        self, file_service, temp_dirs
    ):
        """Test that album is None when parsed from filename."""
        source_dir, _ = temp_dirs

        audio_file = source_dir / "Artist - Track.mp3"
        audio_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.album is None

    def test_get_tracks_sets_year_to_none_for_parsed_filenames(
        self, file_service, temp_dirs
    ):
        """Test that year is None when parsed from filename."""
        source_dir, _ = temp_dirs

        audio_file = source_dir / "Artist - Track.mp3"
        audio_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.year is None

    def test_get_tracks_with_empty_files(self, file_service, temp_dirs):
        """Test handling of empty audio files."""
        source_dir, _ = temp_dirs

        # Create empty audio file
        empty_file = source_dir / "empty.mp3"
        empty_file.touch()

        # Create normal file
        normal_file = source_dir / "Artist - Track.mp3"
        normal_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        # Should still process both files
        assert len(tracks) == 2

    def test_get_tracks_returns_empty_list_on_scan_error(self, file_service, temp_dirs):
        """Test that empty list is returned on directory scan error."""
        source_dir, _ = temp_dirs

        # Use a non-existent directory
        non_existent = source_dir / "does_not_exist"

        tracks = file_service.get_tracks_with_metadata(non_existent)

        assert isinstance(tracks, list)
        assert len(tracks) == 0

    def test_get_tracks_calls_scan_directory(self, file_service, temp_dirs):
        """Test that scan_directory is called internally."""
        source_dir, _ = temp_dirs

        (source_dir / "track.mp3").write_text("audio data")

        with patch.object(file_service, "scan_directory") as mock_scan:
            # Configure mock to return a basic FileInfo
            from tidal_cleanup.models.models import FileInfo

            mock_scan.return_value = [
                FileInfo(
                    path=source_dir / "track.mp3",
                    name="track.mp3",
                    size=100,
                    format=".mp3",
                    duration=180,
                )
            ]

            tracks = file_service.get_tracks_with_metadata(source_dir)

            mock_scan.assert_called_once_with(source_dir)
            assert len(tracks) == 1

    def test_get_tracks_calls_create_track_from_file(self, file_service, temp_dirs):
        """Test that create_track_from_file is called for each file."""
        source_dir, _ = temp_dirs

        (source_dir / "track1.mp3").write_text("audio data")
        (source_dir / "track2.mp3").write_text("audio data")

        with patch.object(file_service, "create_track_from_file") as mock_create:
            # Return None to trigger fallback parsing
            mock_create.return_value = None

            tracks = file_service.get_tracks_with_metadata(source_dir)

            # Should be called once for each file
            assert mock_create.call_count == 2
            # Tracks should still be created via fallback
            assert len(tracks) == 2

    def test_get_tracks_with_unicode_filenames(self, file_service, temp_dirs):
        """Test handling filenames with unicode characters."""
        source_dir, _ = temp_dirs

        # Create files with unicode characters
        unicode_file = source_dir / "Björk - Café.mp3"
        unicode_file.write_text("audio data")

        tracks = file_service.get_tracks_with_metadata(source_dir)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.artist == "Björk"
        assert track.title == "Café"

    def test_get_tracks_preserves_order(self, file_service, temp_dirs):
        """Test that tracks are returned in consistent order."""
        source_dir, _ = temp_dirs

        # Create multiple files
        for i in range(5):
            (source_dir / f"track{i}.mp3").write_text("audio data")

        tracks1 = file_service.get_tracks_with_metadata(source_dir)
        tracks2 = file_service.get_tracks_with_metadata(source_dir)

        # File paths should be in same order (though not necessarily alphabetical)
        paths1 = [str(t.file_path) for t in tracks1]
        paths2 = [str(t.file_path) for t in tracks2]
        assert paths1 == paths2


class TestDeleteFile:
    """Tests for delete_file method."""

    def test_delete_file_non_interactive(self, file_service, temp_dirs):
        """Test deleting a file without user interaction."""
        source_dir, target_dir = temp_dirs

        # Create a file to delete
        test_file = source_dir / "to_delete.txt"
        test_file.write_text("delete me")

        assert test_file.exists()

        # Delete without confirmation
        result = file_service.delete_file(test_file, interactive=False)

        assert result is True
        assert not test_file.exists()

    def test_delete_file_interactive_yes(self, file_service, temp_dirs):
        """Test deleting a file with user confirmation (yes)."""
        source_dir, target_dir = temp_dirs

        # Create a file to delete
        test_file = source_dir / "to_delete.txt"
        test_file.write_text("delete me")

        assert test_file.exists()

        # Mock user input to confirm deletion
        with patch("builtins.input", return_value="y"):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is True
        assert not test_file.exists()

    def test_delete_file_interactive_yes_full(self, file_service, temp_dirs):
        """Test deleting with full 'yes' response."""
        source_dir, target_dir = temp_dirs

        test_file = source_dir / "to_delete.txt"
        test_file.write_text("delete me")

        with patch("builtins.input", return_value="yes"):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is True
        assert not test_file.exists()

    def test_delete_file_interactive_no(self, file_service, temp_dirs):
        """Test canceling deletion with user input (no)."""
        source_dir, target_dir = temp_dirs

        # Create a file
        test_file = source_dir / "keep_me.txt"
        test_file.write_text("keep me")

        assert test_file.exists()

        # Mock user input to cancel deletion
        with patch("builtins.input", return_value="n"):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is False
        assert test_file.exists()  # File should still exist

    def test_delete_file_interactive_no_full(self, file_service, temp_dirs):
        """Test canceling with full 'no' response."""
        source_dir, target_dir = temp_dirs

        test_file = source_dir / "keep_me.txt"
        test_file.write_text("keep me")

        with patch("builtins.input", return_value="no"):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is False
        assert test_file.exists()

    def test_delete_file_interactive_empty_input(self, file_service, temp_dirs):
        """Test canceling with empty input (defaults to no)."""
        source_dir, target_dir = temp_dirs

        test_file = source_dir / "keep_me.txt"
        test_file.write_text("keep me")

        with patch("builtins.input", return_value=""):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is False
        assert test_file.exists()

    def test_delete_file_interactive_random_input(self, file_service, temp_dirs):
        """Test canceling with random input (anything not y/yes)."""
        source_dir, target_dir = temp_dirs

        test_file = source_dir / "keep_me.txt"
        test_file.write_text("keep me")

        with patch("builtins.input", return_value="maybe"):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is False
        assert test_file.exists()

    def test_delete_nonexistent_file(self, file_service, temp_dirs, caplog):
        """Test attempting to delete a file that doesn't exist."""
        source_dir, target_dir = temp_dirs

        nonexistent_file = source_dir / "does_not_exist.txt"

        result = file_service.delete_file(nonexistent_file, interactive=False)

        assert result is False
        assert "File does not exist" in caplog.text

    def test_delete_file_with_permission_error(self, file_service, temp_dirs, caplog):
        """Test handling permission errors during deletion."""
        source_dir, target_dir = temp_dirs

        test_file = source_dir / "protected.txt"
        test_file.write_text("protected")

        # Mock unlink to raise permission error
        with patch.object(Path, "unlink", side_effect=PermissionError("No permission")):
            result = file_service.delete_file(test_file, interactive=False)

        assert result is False
        assert "Failed to delete" in caplog.text

    def test_delete_file_in_subdirectory(self, file_service, temp_dirs):
        """Test deleting a file in a subdirectory."""
        source_dir, target_dir = temp_dirs

        # Create subdirectory structure
        subdir = source_dir / "music" / "artist"
        subdir.mkdir(parents=True)
        test_file = subdir / "song.mp3"
        test_file.write_text("music data")

        assert test_file.exists()

        result = file_service.delete_file(test_file, interactive=False)

        assert result is True
        assert not test_file.exists()

    def test_delete_file_case_insensitive_input(self, file_service, temp_dirs):
        """Test that input is case-insensitive."""
        source_dir, target_dir = temp_dirs

        test_file = source_dir / "to_delete.txt"
        test_file.write_text("delete me")

        # Test uppercase Y
        with patch("builtins.input", return_value="Y"):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is True
        assert not test_file.exists()

        # Test mixed case YES
        test_file2 = source_dir / "to_delete2.txt"
        test_file2.write_text("delete me too")

        with patch("builtins.input", return_value="YeS"):
            result = file_service.delete_file(test_file2, interactive=True)

        assert result is True
        assert not test_file2.exists()

    def test_delete_file_with_whitespace_in_input(self, file_service, temp_dirs):
        """Test that whitespace is stripped from input."""
        source_dir, target_dir = temp_dirs

        test_file = source_dir / "to_delete.txt"
        test_file.write_text("delete me")

        # Test with leading/trailing whitespace
        with patch("builtins.input", return_value="  y  "):
            result = file_service.delete_file(test_file, interactive=True)

        assert result is True
        assert not test_file.exists()

    def test_delete_large_file(self, file_service, temp_dirs):
        """Test deleting a large file."""
        source_dir, target_dir = temp_dirs

        # Create a larger file
        large_file = source_dir / "large.bin"
        large_file.write_bytes(b"x" * 10_000_000)  # 10 MB

        assert large_file.exists()
        assert large_file.stat().st_size == 10_000_000

        result = file_service.delete_file(large_file, interactive=False)

        assert result is True
        assert not large_file.exists()

    def test_delete_multiple_files_sequentially(self, file_service, temp_dirs):
        """Test deleting multiple files one after another."""
        source_dir, target_dir = temp_dirs

        # Create multiple files
        files = [source_dir / f"file{i}.txt" for i in range(5)]
        for f in files:
            f.write_text("content")

        # Delete all files
        for f in files:
            result = file_service.delete_file(f, interactive=False)
            assert result is True
            assert not f.exists()

    def test_delete_file_logs_correctly(self, file_service, temp_dirs, caplog):
        """Test that deletion is logged correctly."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, target_dir = temp_dirs

        test_file = source_dir / "to_delete.txt"
        test_file.write_text("delete me")

        file_service.delete_file(test_file, interactive=False)

        assert "Deleted:" in caplog.text
        assert str(test_file) in caplog.text

    def test_delete_file_cancellation_logged(self, file_service, temp_dirs, caplog):
        """Test that cancellation is logged correctly."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, target_dir = temp_dirs

        test_file = source_dir / "keep_me.txt"
        test_file.write_text("keep me")

        with patch("builtins.input", return_value="n"):
            file_service.delete_file(test_file, interactive=True)

        assert "Deletion cancelled by user" in caplog.text


class TestConvertDirectory:
    """Tests for convert_directory method."""

    def test_convert_directory_with_playlists_subdir(self, file_service, temp_dirs):
        """Test convert_directory with proper Playlists subdirectory structure."""
        source_dir, target_dir = temp_dirs

        # Create Playlists subdirectory structure
        playlist1_source = source_dir / "Playlists" / "Favorites"
        playlist1_source.mkdir(parents=True)
        playlist2_source = source_dir / "Playlists" / "Workout"
        playlist2_source.mkdir(parents=True)

        # Create some source files
        (playlist1_source / "track1.m4a").write_text("audio1")
        (playlist1_source / "track2.m4a").write_text("audio2")
        (playlist2_source / "track3.m4a").write_text("audio3")

        # Mock convert_audio to avoid actual conversion
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="2"
            )

        # Verify results
        assert "Favorites" in result
        assert "Workout" in result
        assert len(result["Favorites"]) == 2  # 2 files converted
        assert len(result["Workout"]) == 1  # 1 file converted
        assert mock_convert.call_count == 3  # Total conversions

    def test_convert_directory_without_playlists_subdir(
        self, file_service, temp_dirs, caplog
    ):
        """Test convert_directory falls back to direct directory scanning."""
        import logging

        caplog.set_level(logging.WARNING)

        source_dir, target_dir = temp_dirs

        # Create playlist directories directly (no Playlists subdirectory)
        playlist1_source = source_dir / "Favorites"
        playlist1_source.mkdir(parents=True)
        playlist2_source = source_dir / "Workout"
        playlist2_source.mkdir(parents=True)

        # Create some source files
        (playlist1_source / "track1.m4a").write_text("audio1")
        (playlist2_source / "track2.m4a").write_text("audio2")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="2"
            )

        # Verify fallback warning was logged
        assert "No 'Playlists' directory found" in caplog.text
        assert "falling back to direct directory scanning" in caplog.text

        # Verify results
        assert "Favorites" in result
        assert "Workout" in result
        assert mock_convert.call_count == 2

    def test_convert_directory_empty_source(self, file_service, temp_dirs, caplog):
        """Test convert_directory with empty source directory."""
        import logging

        caplog.set_level(logging.WARNING)

        source_dir, target_dir = temp_dirs

        result = file_service.convert_directory(
            source_dir, target_dir, target_format=".mp3", quality="2"
        )

        # Should return empty dict
        assert result == {}

    def test_convert_directory_with_subdirectories(self, file_service, temp_dirs):
        """Test convert_directory handles nested subdirectories correctly."""
        source_dir, target_dir = temp_dirs

        # Create nested structure
        playlist_source = source_dir / "Playlists" / "MyPlaylist"
        subdir1 = playlist_source / "subdir1"
        subdir2 = playlist_source / "subdir2"
        subdir1.mkdir(parents=True)
        subdir2.mkdir(parents=True)

        # Create files in subdirectories
        (subdir1 / "track1.m4a").write_text("audio1")
        (subdir2 / "track2.m4a").write_text("audio2")
        (playlist_source / "track3.m4a").write_text("audio3")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="2"
            )

        # Verify all files were converted
        assert "MyPlaylist" in result
        assert len(result["MyPlaylist"]) == 3
        assert mock_convert.call_count == 3

    def test_convert_directory_with_existing_target_files(
        self, file_service, temp_dirs
    ):
        """Test convert_directory skips files that already exist in target."""
        source_dir, target_dir = temp_dirs

        # Create source playlist
        playlist_source = source_dir / "Playlists" / "MyPlaylist"
        playlist_source.mkdir(parents=True)
        (playlist_source / "track1.m4a").write_text("audio1")
        (playlist_source / "track2.m4a").write_text("audio2")

        # Create target playlist with one existing file
        playlist_target = target_dir / "Playlists" / "MyPlaylist"
        playlist_target.mkdir(parents=True)
        (playlist_target / "track1.mp3").write_text("converted1")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="2"
            )

        # Verify only track2 was converted, track1 was skipped
        assert "MyPlaylist" in result
        assert len(result["MyPlaylist"]) == 2  # 1 converted + 1 skipped
        assert mock_convert.call_count == 1  # Only track2 converted

        # Check that we have both a converted job and a skipped job
        jobs = result["MyPlaylist"]
        skipped_jobs = [j for j in jobs if j.was_skipped]
        converted_jobs = [j for j in jobs if not j.was_skipped]
        assert len(skipped_jobs) == 1
        assert len(converted_jobs) == 1

    def test_convert_directory_deletes_orphaned_target_files(
        self, file_service, temp_dirs
    ):
        """Test convert_directory deletes files in target that don't exist in source."""
        source_dir, target_dir = temp_dirs

        # Create source playlist with one file
        playlist_source = source_dir / "Playlists" / "MyPlaylist"
        playlist_source.mkdir(parents=True)
        (playlist_source / "track1.m4a").write_text("audio1")

        # Create target playlist with additional orphaned file
        playlist_target = target_dir / "Playlists" / "MyPlaylist"
        playlist_target.mkdir(parents=True)
        orphaned_file = playlist_target / "track2.mp3"
        orphaned_file.write_text("old converted file")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="2"
            )

        # Verify orphaned file was deleted
        assert not orphaned_file.exists()

        # Verify we have a deletion job
        assert "MyPlaylist" in result
        jobs = result["MyPlaylist"]
        deleted_jobs = [j for j in jobs if j.status == "deleted"]
        assert len(deleted_jobs) == 1

    def test_convert_directory_multiple_playlists_mixed_operations(
        self, file_service, temp_dirs
    ):
        """Test convert_directory with multiple playlists and mixed operations."""
        source_dir, target_dir = temp_dirs

        # Create multiple playlists with different scenarios
        # Playlist 1: All new files
        playlist1_source = source_dir / "Playlists" / "NewPlaylist"
        playlist1_source.mkdir(parents=True)
        (playlist1_source / "new1.m4a").write_text("audio1")
        (playlist1_source / "new2.m4a").write_text("audio2")

        # Playlist 2: Mix of new and existing files
        playlist2_source = source_dir / "Playlists" / "MixedPlaylist"
        playlist2_source.mkdir(parents=True)
        (playlist2_source / "new.m4a").write_text("audio3")
        (playlist2_source / "existing.m4a").write_text("audio4")

        playlist2_target = target_dir / "Playlists" / "MixedPlaylist"
        playlist2_target.mkdir(parents=True)
        (playlist2_target / "existing.mp3").write_text("converted")
        (playlist2_target / "orphaned.mp3").write_text("old")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="2"
            )

        # Verify all playlists processed
        assert "NewPlaylist" in result
        assert "MixedPlaylist" in result

        # NewPlaylist: 2 conversions
        assert len(result["NewPlaylist"]) == 2
        assert mock_convert.call_count == 3  # 2 from NewPlaylist + 1 from MixedPlaylist

        # MixedPlaylist: 1 conversion + 1 skip + 1 deletion
        assert len(result["MixedPlaylist"]) == 3

    def test_convert_directory_with_custom_quality(self, file_service, temp_dirs):
        """Test convert_directory respects custom quality parameter."""
        source_dir, target_dir = temp_dirs

        playlist_source = source_dir / "Playlists" / "MyPlaylist"
        playlist_source.mkdir(parents=True)
        (playlist_source / "track1.m4a").write_text("audio1")

        # Mock convert_audio to capture parameters
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="5",
                status="completed",
            )

            file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="5"
            )

        # Verify quality parameter was passed correctly
        assert mock_convert.call_count == 1
        call_args = mock_convert.call_args
        # Quality is the third positional argument (after source_path and target_path)
        assert call_args[0][2] == "5"

    def test_convert_directory_with_custom_target_format(self, file_service, temp_dirs):
        """Test convert_directory respects custom target format parameter."""
        source_dir, target_dir = temp_dirs

        playlist_source = source_dir / "Playlists" / "MyPlaylist"
        playlist_source.mkdir(parents=True)
        (playlist_source / "track1.m4a").write_text("audio1")

        # Mock convert_audio to capture parameters
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.flac"),
                source_format=".m4a",
                target_format=".flac",
                quality="2",
                status="completed",
            )

            file_service.convert_directory(
                source_dir, target_dir, target_format=".flac", quality="2"
            )

        # Verify target format was used
        assert mock_convert.call_count == 1
        call_args = mock_convert.call_args
        target_path = call_args[0][1]  # Second positional argument
        assert target_path.suffix == ".flac"

    def test_convert_directory_logging(self, file_service, temp_dirs, caplog):
        """Test convert_directory logs conversion info correctly."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, target_dir = temp_dirs

        playlist_source = source_dir / "Playlists" / "MyPlaylist"
        playlist_source.mkdir(parents=True)
        (playlist_source / "track1.m4a").write_text("audio1")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            file_service.convert_directory(
                source_dir, target_dir, target_format=".mp3", quality="2"
            )

        # Verify logging
        assert "Converting files from" in caplog.text
        assert str(source_dir) in caplog.text
        assert str(target_dir) in caplog.text
        assert "diff-based optimization" in caplog.text

    def test_convert_directory_with_playlist_filter_exact_match(
        self, file_service, temp_dirs
    ):
        """Test converting with playlist filter using exact match."""
        source_dir, target_dir = temp_dirs

        # Create multiple playlists
        playlists = ["House Music", "Techno", "Deep House"]
        for playlist_name in playlists:
            playlist_dir = source_dir / "Playlists" / playlist_name
            playlist_dir.mkdir(parents=True)
            (playlist_dir / "track.m4a").write_text("audio")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, playlist_filter="House Music"
            )

        # Should only convert the exact match
        assert len(result) == 1
        assert "House Music" in result
        assert "Techno" not in result
        assert "Deep House" not in result

    def test_convert_directory_with_playlist_filter_fuzzy_match(
        self, file_service, temp_dirs
    ):
        """Test converting with playlist filter using fuzzy matching."""
        source_dir, target_dir = temp_dirs

        # Create playlists
        playlists = ["House Music 2024", "Techno Classics", "Deep House Vibes"]
        for playlist_name in playlists:
            playlist_dir = source_dir / "Playlists" / playlist_name
            playlist_dir.mkdir(parents=True)
            (playlist_dir / "track.m4a").write_text("audio")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            # Search for "House Music" - should match "House Music 2024"
            result = file_service.convert_directory(
                source_dir, target_dir, playlist_filter="House Music"
            )

        assert len(result) == 1
        assert "House Music 2024" in result

    def test_convert_directory_with_playlist_filter_no_match(
        self, file_service, temp_dirs
    ):
        """Test converting with playlist filter when no match is found."""
        source_dir, target_dir = temp_dirs

        # Create playlists
        playlists = ["House Music", "Techno"]
        for playlist_name in playlists:
            playlist_dir = source_dir / "Playlists" / playlist_name
            playlist_dir.mkdir(parents=True)
            (playlist_dir / "track.m4a").write_text("audio")

        result = file_service.convert_directory(
            source_dir, target_dir, playlist_filter="Jazz Favorites"
        )

        # Should return empty dict when no match
        assert len(result) == 0

    def test_convert_directory_with_playlist_filter_case_insensitive(
        self, file_service, temp_dirs
    ):
        """Test playlist filter is case-insensitive."""
        source_dir, target_dir = temp_dirs

        playlist_dir = source_dir / "Playlists" / "House Music"
        playlist_dir.mkdir(parents=True)
        (playlist_dir / "track.m4a").write_text("audio")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(
                source_dir, target_dir, playlist_filter="house music"
            )

        assert len(result) == 1
        assert "House Music" in result

    def test_convert_directory_with_playlist_filter_partial_match(
        self, file_service, temp_dirs
    ):
        """Test playlist filter with partial name matching."""
        source_dir, target_dir = temp_dirs

        # Create playlists
        playlists = ["My House Music Collection", "Techno", "House Party"]
        for playlist_name in playlists:
            playlist_dir = source_dir / "Playlists" / playlist_name
            playlist_dir.mkdir(parents=True)
            (playlist_dir / "track.m4a").write_text("audio")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            # "House" should match one of the house playlists
            result = file_service.convert_directory(
                source_dir, target_dir, playlist_filter="House"
            )

        # Should match one playlist (best match)
        assert len(result) == 1
        assert any("House" in name for name in result.keys())

    def test_convert_directory_without_playlist_filter_converts_all(
        self, file_service, temp_dirs
    ):
        """Test that without filter, all playlists are converted."""
        source_dir, target_dir = temp_dirs

        # Create multiple playlists
        playlists = ["House", "Techno", "Trance"]
        for playlist_name in playlists:
            playlist_dir = source_dir / "Playlists" / playlist_name
            playlist_dir.mkdir(parents=True)
            (playlist_dir / "track.m4a").write_text("audio")

        # Mock convert_audio
        with patch.object(file_service, "convert_audio") as mock_convert:
            mock_convert.return_value = ConversionJob(
                source_path=Path("dummy.m4a"),
                target_path=Path("dummy.mp3"),
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            result = file_service.convert_directory(source_dir, target_dir)

        # All playlists should be converted
        assert len(result) == 3
        assert "House" in result
        assert "Techno" in result
        assert "Trance" in result


class TestFilterPlaylistByName:
    """Tests for _filter_playlist_by_name method."""

    def test_filter_exact_match(self, file_service, temp_dirs):
        """Test filtering with exact playlist name match."""
        source_dir, _ = temp_dirs

        # Create playlists
        playlists = ["House Music", "Techno", "Deep House"]
        playlist_dirs = []
        for name in playlists:
            playlist_dir = source_dir / name
            playlist_dir.mkdir()
            playlist_dirs.append(playlist_dir)

        result = file_service._filter_playlist_by_name(playlist_dirs, "House Music")

        assert len(result) == 1
        assert result[0].name == "House Music"

    def test_filter_exact_match_case_insensitive(self, file_service, temp_dirs):
        """Test exact match is case-insensitive."""
        source_dir, _ = temp_dirs

        playlist_dir = source_dir / "House Music"
        playlist_dir.mkdir()

        result = file_service._filter_playlist_by_name([playlist_dir], "house music")

        assert len(result) == 1
        assert result[0].name == "House Music"

    def test_filter_fuzzy_match_with_typo(self, file_service, temp_dirs):
        """Test fuzzy matching handles typos."""
        source_dir, _ = temp_dirs

        playlist_dir = source_dir / "House Music"
        playlist_dir.mkdir()

        # Typo: "Musik" instead of "Music"
        result = file_service._filter_playlist_by_name([playlist_dir], "House Musik")

        assert len(result) == 1
        assert result[0].name == "House Music"

    def test_filter_fuzzy_match_partial_name(self, file_service, temp_dirs):
        """Test fuzzy matching with partial name."""
        source_dir, _ = temp_dirs

        playlists = ["House Music 2024", "Techno", "House Party"]
        playlist_dirs = []
        for name in playlists:
            playlist_dir = source_dir / name
            playlist_dir.mkdir()
            playlist_dirs.append(playlist_dir)

        result = file_service._filter_playlist_by_name(playlist_dirs, "House Music")

        # Should match "House Music 2024" as best match
        assert len(result) == 1
        assert "House Music" in result[0].name

    def test_filter_fuzzy_match_word_order(self, file_service, temp_dirs):
        """Test fuzzy matching handles different word order."""
        source_dir, _ = temp_dirs

        playlist_dir = source_dir / "Music House Collection"
        playlist_dir.mkdir()

        result = file_service._filter_playlist_by_name([playlist_dir], "House Music")

        assert len(result) == 1
        assert result[0].name == "Music House Collection"

    def test_filter_no_match_below_threshold(self, file_service, temp_dirs):
        """Test no match returned when similarity is too low."""
        source_dir, _ = temp_dirs

        playlists = ["Jazz Classics", "Blues Standards"]
        playlist_dirs = []
        for name in playlists:
            playlist_dir = source_dir / name
            playlist_dir.mkdir()
            playlist_dirs.append(playlist_dir)

        result = file_service._filter_playlist_by_name(playlist_dirs, "Techno")

        # No match should be found
        assert len(result) == 0

    def test_filter_empty_playlist_list(self, file_service, temp_dirs):
        """Test filtering with empty playlist list."""
        result = file_service._filter_playlist_by_name([], "House Music")

        assert len(result) == 0

    def test_filter_returns_best_match_from_multiple(self, file_service, temp_dirs):
        """Test that only the best match is returned from multiple candidates."""
        source_dir, _ = temp_dirs

        playlists = ["House", "House Music", "House Music 2024"]
        playlist_dirs = []
        for name in playlists:
            playlist_dir = source_dir / name
            playlist_dir.mkdir()
            playlist_dirs.append(playlist_dir)

        result = file_service._filter_playlist_by_name(
            playlist_dirs, "House Music 2024"
        )

        # Should return exact match
        assert len(result) == 1
        assert result[0].name == "House Music 2024"

    def test_filter_with_special_characters(self, file_service, temp_dirs):
        """Test filtering with special characters in names."""
        source_dir, _ = temp_dirs

        playlist_dir = source_dir / "House & Techno"
        playlist_dir.mkdir()

        result = file_service._filter_playlist_by_name([playlist_dir], "House Techno")

        assert len(result) == 1
        assert result[0].name == "House & Techno"

    def test_filter_logs_exact_match(self, file_service, temp_dirs, caplog):
        """Test that exact match is logged."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, _ = temp_dirs
        playlist_dir = source_dir / "House Music"
        playlist_dir.mkdir()

        file_service._filter_playlist_by_name([playlist_dir], "House Music")

        assert "Found exact match for playlist: House Music" in caplog.text

    def test_filter_logs_fuzzy_match_with_score(self, file_service, temp_dirs, caplog):
        """Test that fuzzy match logs include similarity score."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, _ = temp_dirs
        playlist_dir = source_dir / "House Music 2024"
        playlist_dir.mkdir()

        file_service._filter_playlist_by_name([playlist_dir], "House Music")

        assert "Found fuzzy match" in caplog.text
        assert "score:" in caplog.text

    def test_filter_logs_warning_when_no_match(self, file_service, temp_dirs, caplog):
        """Test that warning is logged when no match found."""
        import logging

        caplog.set_level(logging.WARNING)

        source_dir, _ = temp_dirs
        playlist_dir = source_dir / "Jazz"
        playlist_dir.mkdir()

        file_service._filter_playlist_by_name([playlist_dir], "Techno")

        assert "No playlist found matching 'Techno'" in caplog.text


class TestReplaceWithEmptyFile:
    """Tests for _replace_with_empty_file method."""

    def test_replace_existing_file_with_empty(self, file_service, temp_dirs):
        """Test replacing an existing file with an empty file."""
        source_dir, _ = temp_dirs

        # Create a file with content
        test_file = source_dir / "test_file.txt"
        test_file.write_text("This is some content")
        original_size = test_file.stat().st_size
        assert original_size > 0

        # Replace with empty file
        file_service._replace_with_empty_file(test_file)

        # Verify file still exists but is empty
        assert test_file.exists()
        assert test_file.stat().st_size == 0

    def test_replace_preserves_file_location(self, file_service, temp_dirs):
        """Test that replace preserves the file path."""
        source_dir, _ = temp_dirs

        test_file = source_dir / "test_file.m4a"
        test_file.write_text("audio data")

        file_service._replace_with_empty_file(test_file)

        # File should still exist at the same location
        assert test_file.exists()
        assert test_file.parent == source_dir

    def test_replace_with_empty_file_in_subdirectory(self, file_service, temp_dirs):
        """Test replacing a file in a subdirectory."""
        source_dir, _ = temp_dirs

        # Create subdirectory structure
        subdir = source_dir / "subdir1" / "subdir2"
        subdir.mkdir(parents=True)
        test_file = subdir / "nested_file.m4a"
        test_file.write_text("nested audio data")

        file_service._replace_with_empty_file(test_file)

        # Verify file is empty but location preserved
        assert test_file.exists()
        assert test_file.stat().st_size == 0
        assert test_file.parent == subdir

    def test_replace_already_empty_file(self, file_service, temp_dirs):
        """Test replacing a file that is already empty."""
        source_dir, _ = temp_dirs

        # Create an empty file
        test_file = source_dir / "empty_file.txt"
        test_file.touch()
        assert test_file.stat().st_size == 0

        # Replace with empty file (should work without error)
        file_service._replace_with_empty_file(test_file)

        # File should still exist and be empty
        assert test_file.exists()
        assert test_file.stat().st_size == 0

    def test_replace_logs_debug_message(self, file_service, temp_dirs, caplog):
        """Test that successful replacement logs a debug message."""
        import logging

        caplog.set_level(logging.DEBUG)

        source_dir, _ = temp_dirs

        test_file = source_dir / "test_file.txt"
        test_file.write_text("content")

        file_service._replace_with_empty_file(test_file)

        # Verify debug log
        assert "Replaced" in caplog.text
        assert str(test_file) in caplog.text
        assert "with empty file" in caplog.text

    def test_replace_nonexistent_file_logs_warning(
        self, file_service, temp_dirs, caplog
    ):
        """Test that attempting to replace nonexistent file logs warning."""
        import logging

        caplog.set_level(logging.WARNING)

        source_dir, _ = temp_dirs

        # Try to replace a file that doesn't exist
        nonexistent_file = source_dir / "does_not_exist.txt"

        file_service._replace_with_empty_file(nonexistent_file)

        # Should log a warning
        assert "Failed to replace file with empty" in caplog.text

    def test_replace_with_permission_error(self, file_service, temp_dirs, caplog):
        """Test handling of permission errors during replacement."""
        import contextlib
        import logging
        import os
        import platform
        import stat

        caplog.set_level(logging.WARNING)

        source_dir, _ = temp_dirs

        test_file = source_dir / "readonly_file.txt"
        test_file.write_text("content")

        # Make directory read-only (file can't be deleted)
        # Windows handles permissions differently
        if platform.system() == "Windows":
            # On Windows, make the file itself read-only
            os.chmod(test_file, stat.S_IREAD)
            os.chmod(source_dir, stat.S_IREAD | stat.S_IEXEC)
        else:
            os.chmod(source_dir, 0o444)

        try:
            file_service._replace_with_empty_file(test_file)

            # Should log warning about failure
            assert "Failed to replace file with empty" in caplog.text
        finally:
            # Restore permissions for cleanup
            if platform.system() == "Windows":
                os.chmod(source_dir, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
                with contextlib.suppress(FileNotFoundError):
                    os.chmod(test_file, stat.S_IWRITE | stat.S_IREAD)
            else:
                os.chmod(source_dir, 0o755)  # nosec B103

    def test_replace_multiple_files_independently(self, file_service, temp_dirs):
        """Test replacing multiple files independently."""
        source_dir, _ = temp_dirs

        # Create multiple files
        file1 = source_dir / "file1.txt"
        file2 = source_dir / "file2.txt"
        file3 = source_dir / "file3.txt"

        file1.write_text("content 1")
        file2.write_text("content 2 is longer")
        file3.write_text("c")

        # Replace each file
        file_service._replace_with_empty_file(file1)
        file_service._replace_with_empty_file(file2)
        file_service._replace_with_empty_file(file3)

        # All should be empty
        assert file1.stat().st_size == 0
        assert file2.stat().st_size == 0
        assert file3.stat().st_size == 0

    def test_replace_with_different_file_types(self, file_service, temp_dirs):
        """Test replacing files of different types."""
        source_dir, _ = temp_dirs

        # Create files with different extensions
        mp3_file = source_dir / "audio.mp3"
        m4a_file = source_dir / "audio.m4a"
        txt_file = source_dir / "text.txt"

        mp3_file.write_text("mp3 data")
        m4a_file.write_text("m4a data")
        txt_file.write_text("text data")

        # Replace all
        file_service._replace_with_empty_file(mp3_file)
        file_service._replace_with_empty_file(m4a_file)
        file_service._replace_with_empty_file(txt_file)

        # All should be empty, extensions preserved
        assert mp3_file.exists() and mp3_file.suffix == ".mp3"
        assert m4a_file.exists() and m4a_file.suffix == ".m4a"
        assert txt_file.exists() and txt_file.suffix == ".txt"
        assert mp3_file.stat().st_size == 0
        assert m4a_file.stat().st_size == 0
        assert txt_file.stat().st_size == 0

    def test_replace_preserves_file_name(self, file_service, temp_dirs):
        """Test that replacement preserves the original filename."""
        source_dir, _ = temp_dirs

        original_name = "my_special_file_name.m4a"
        test_file = source_dir / original_name
        test_file.write_text("audio content")

        file_service._replace_with_empty_file(test_file)

        # File name should be unchanged
        assert test_file.name == original_name
        assert test_file.exists()
        assert test_file.stat().st_size == 0


class TestConvertAudio:
    """Tests for convert_audio method and its helper methods."""

    def test_build_ffmpeg_command(self, file_service, temp_dirs):
        """Test FFmpeg command building."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "3")

        assert cmd == [
            "ffmpeg",
            "-nostdin",
            "-i",
            str(source_file),
            "-q:a",
            "3",
            str(target_file),
        ]

    def test_build_ffmpeg_command_with_different_quality(self, file_service, temp_dirs):
        """Test FFmpeg command with different quality settings."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "9")

        assert "-q:a" in cmd
        assert "9" in cmd

    def test_build_ffmpeg_command_returns_list(self, file_service, temp_dirs):
        """Test that _build_ffmpeg_command returns a list."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        assert isinstance(cmd, list)
        assert all(isinstance(item, str) for item in cmd)

    def test_build_ffmpeg_command_with_all_quality_levels(
        self, file_service, temp_dirs
    ):
        """Test FFmpeg command building with all valid quality levels (0-9)."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        for quality in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            cmd = file_service._build_ffmpeg_command(source_file, target_file, quality)

            assert "ffmpeg" in cmd
            assert "-nostdin" in cmd
            assert "-i" in cmd
            assert str(source_file) in cmd
            assert "-q:a" in cmd
            assert quality in cmd
            assert str(target_file) in cmd

    def test_build_ffmpeg_command_correct_argument_order(self, file_service, temp_dirs):
        """Test that FFmpeg command has arguments in correct order."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        # Check order of critical arguments
        assert cmd[0] == "ffmpeg"
        assert cmd[1] == "-nostdin"
        assert cmd[2] == "-i"
        assert cmd[3] == str(source_file)
        assert cmd[4] == "-q:a"
        assert cmd[5] == "2"
        assert cmd[6] == str(target_file)
        assert len(cmd) == 7

    def test_build_ffmpeg_command_with_different_source_formats(
        self, file_service, temp_dirs
    ):
        """Test FFmpeg command with various source audio formats."""
        source_dir, target_dir = temp_dirs

        source_formats = [".m4a", ".mp4", ".flac", ".wav", ".aac", ".mp3"]

        for source_format in source_formats:
            source_file = source_dir / f"audio{source_format}"
            target_file = target_dir / "audio.mp3"

            cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

            assert str(source_file) in cmd
            assert source_format in str(source_file)

    def test_build_ffmpeg_command_with_different_target_formats(
        self, file_service, temp_dirs
    ):
        """Test FFmpeg command with various target audio formats."""
        source_dir, target_dir = temp_dirs

        target_formats = [".mp3", ".flac", ".wav", ".aac"]

        for target_format in target_formats:
            source_file = source_dir / "audio.m4a"
            target_file = target_dir / f"audio{target_format}"

            cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

            assert str(target_file) in cmd
            assert target_format in str(target_file)

    def test_build_ffmpeg_command_with_special_characters_in_path(
        self, file_service, temp_dirs
    ):
        """Test FFmpeg command with special characters in file paths."""
        source_dir, target_dir = temp_dirs

        # Filenames with spaces, unicode, and special chars
        source_file = source_dir / "Artist - Track (2024) & Friends.m4a"
        target_file = target_dir / "Artist - Track (2024) & Friends.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        assert str(source_file) in cmd
        assert str(target_file) in cmd
        # Paths should be converted to strings properly
        assert isinstance(cmd[3], str)
        assert isinstance(cmd[6], str)

    def test_build_ffmpeg_command_with_nested_directories(
        self, file_service, temp_dirs
    ):
        """Test FFmpeg command with nested directory structures."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "artist" / "album" / "track.m4a"
        target_file = target_dir / "artist" / "album" / "track.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        assert str(source_file) in cmd
        assert str(target_file) in cmd
        assert "artist" in str(source_file)
        assert "album" in str(source_file)

    def test_build_ffmpeg_command_nostdin_flag_present(self, file_service, temp_dirs):
        """Test that -nostdin flag is always present to prevent interactive prompts."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        # -nostdin should be present to prevent ffmpeg from waiting for user input
        assert "-nostdin" in cmd
        # It should be the first flag after ffmpeg
        assert cmd.index("-nostdin") == 1

    def test_build_ffmpeg_command_with_absolute_paths(self, file_service, temp_dirs):
        """Test FFmpeg command with absolute paths."""
        source_dir, target_dir = temp_dirs

        source_file = (source_dir / "audio.m4a").resolve()
        target_file = (target_dir / "audio.mp3").resolve()

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        assert str(source_file) in cmd
        assert str(target_file) in cmd
        # Paths should be absolute
        assert source_file.is_absolute()
        assert target_file.is_absolute()

    def test_build_ffmpeg_command_with_unicode_in_filename(
        self, file_service, temp_dirs
    ):
        """Test FFmpeg command with unicode characters in filename."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "Café Müller – Björk.m4a"
        target_file = target_dir / "Café Müller – Björk.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        assert str(source_file) in cmd
        assert str(target_file) in cmd

    def test_build_ffmpeg_command_preserves_path_objects(self, file_service, temp_dirs):
        """Test that Path objects are properly converted to strings."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        # Ensure inputs are Path objects
        assert isinstance(source_file, Path)
        assert isinstance(target_file, Path)

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "2")

        # Command should contain string representations
        assert cmd[3] == str(source_file)
        assert cmd[6] == str(target_file)

    def test_build_ffmpeg_command_quality_as_string(self, file_service, temp_dirs):
        """Test that quality parameter is kept as string in command."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        target_file = target_dir / "audio.mp3"

        cmd = file_service._build_ffmpeg_command(source_file, target_file, "7")

        # Quality should be a string, not an integer
        quality_index = cmd.index("-q:a") + 1
        assert cmd[quality_index] == "7"
        assert isinstance(cmd[quality_index], str)

    def test_handle_empty_source_file(self, file_service, temp_dirs):
        """Test handling of empty source file."""
        source_dir, _ = temp_dirs

        source_file = source_dir / "empty.m4a"
        target_file = source_dir / "empty.mp3"

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_empty_source_file(source_file, job)

        assert result.status == "completed"
        assert result.was_skipped is True

    def test_handle_empty_source_file_logs_warning(
        self, file_service, temp_dirs, caplog
    ):
        """Test that handling empty source file logs warning."""
        import logging

        caplog.set_level(logging.WARNING)

        source_dir, _ = temp_dirs

        source_file = source_dir / "empty.m4a"
        target_file = source_dir / "empty.mp3"

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        file_service._handle_empty_source_file(source_file, job)

        assert "Skipping conversion of empty file" in caplog.text
        assert str(source_file) in caplog.text

    def test_handle_empty_source_file_preserves_job_attributes(
        self, file_service, temp_dirs
    ):
        """Test that empty file handling preserves other job attributes."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "empty.m4a"
        target_file = target_dir / "empty.mp3"

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="5",
        )

        result = file_service._handle_empty_source_file(source_file, job)

        # Check that original job attributes are preserved
        assert result.source_path == source_file
        assert result.target_path == target_file
        assert result.source_format == ".m4a"
        assert result.target_format == ".mp3"
        assert result.quality == "5"

    def test_handle_empty_source_file_returns_same_job_object(
        self, file_service, temp_dirs
    ):
        """Test that the same job object is returned (not a copy)."""
        source_dir, _ = temp_dirs

        source_file = source_dir / "empty.m4a"
        target_file = source_dir / "empty.mp3"

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_empty_source_file(source_file, job)

        # Should return the same object, not a new one
        assert result is job

    def test_handle_empty_source_file_with_different_formats(
        self, file_service, temp_dirs
    ):
        """Test handling empty source file with various format combinations."""
        source_dir, target_dir = temp_dirs

        format_combinations = [
            (".m4a", ".mp3"),
            (".mp4", ".mp3"),
            (".flac", ".mp3"),
            (".wav", ".mp3"),
        ]

        for source_format, target_format in format_combinations:
            source_file = source_dir / f"empty{source_format}"
            target_file = target_dir / f"empty{target_format}"

            job = ConversionJob(
                source_path=source_file,
                target_path=target_file,
                source_format=source_format,
                target_format=target_format,
                quality="2",
            )

            result = file_service._handle_empty_source_file(source_file, job)

            assert result.status == "completed"
            assert result.was_skipped is True

    def test_handle_empty_source_file_with_different_quality_settings(
        self, file_service, temp_dirs
    ):
        """Test that quality setting doesn't affect empty file handling."""
        source_dir, _ = temp_dirs

        source_file = source_dir / "empty.m4a"
        target_file = source_dir / "empty.mp3"

        for quality in ["0", "2", "5", "9"]:
            job = ConversionJob(
                source_path=source_file,
                target_path=target_file,
                source_format=".m4a",
                target_format=".mp3",
                quality=quality,
            )

            result = file_service._handle_empty_source_file(source_file, job)

            assert result.status == "completed"
            assert result.was_skipped is True
            assert result.quality == quality

    def test_handle_empty_source_file_does_not_set_error_message(
        self, file_service, temp_dirs
    ):
        """Test that handling empty source file doesn't set error message."""
        source_dir, _ = temp_dirs

        source_file = source_dir / "empty.m4a"
        target_file = source_dir / "empty.mp3"

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_empty_source_file(source_file, job)

        # Should not have an error message since this is expected behavior
        assert result.error_message is None

    def test_handle_empty_source_file_with_nested_paths(self, file_service, temp_dirs):
        """Test handling empty source file with nested directory paths."""
        source_dir, target_dir = temp_dirs

        # Create nested directories
        nested_source = source_dir / "artist" / "album"
        nested_target = target_dir / "artist" / "album"

        source_file = nested_source / "track.m4a"
        target_file = nested_target / "track.mp3"

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_empty_source_file(source_file, job)

        assert result.status == "completed"
        assert result.was_skipped is True

    def test_handle_empty_source_file_with_special_characters_in_filename(
        self, file_service, temp_dirs
    ):
        """Test handling empty source file with special characters in filename."""
        source_dir, _ = temp_dirs

        # Filename with spaces, unicode, and special chars
        source_file = source_dir / "Track (2024) – Artist & Friends.m4a"
        target_file = source_dir / "Track (2024) – Artist & Friends.mp3"

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_empty_source_file(source_file, job)

        assert result.status == "completed"
        assert result.was_skipped is True

    def test_handle_successful_conversion(self, file_service, temp_dirs):
        """Test handling of successful conversion."""
        source_dir, target_dir = temp_dirs

        # Create source and target files
        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"
        target_file.write_text("converted audio")

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        assert result.status == "completed"
        assert source_file.stat().st_size == 0  # Should be replaced with empty

    def test_handle_successful_conversion_target_not_created(
        self, file_service, temp_dirs
    ):
        """Test handling when target file was not created."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"  # Not created

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        assert result.status == "failed"
        assert result.error_message == "Target file was not created"

    def test_handle_successful_conversion_logs_success(
        self, file_service, temp_dirs, caplog
    ):
        """Test that successful conversion logs info message."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"
        target_file.write_text("converted")

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        file_service._handle_successful_conversion(source_file, target_file, job)

        assert "Successfully converted" in caplog.text
        assert str(source_file) in caplog.text

    def test_handle_successful_conversion_calls_replace_with_empty(
        self, file_service, temp_dirs
    ):
        """Test that successful conversion calls _replace_with_empty_file."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        original_size = source_file.stat().st_size
        target_file = target_dir / "audio.mp3"
        target_file.write_text("converted")

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        assert original_size > 0  # Verify source has content

        file_service._handle_successful_conversion(source_file, target_file, job)

        # Source should be replaced with empty file
        assert source_file.exists()
        assert source_file.stat().st_size == 0

    def test_handle_successful_conversion_preserves_target(
        self, file_service, temp_dirs
    ):
        """Test that successful conversion preserves target file."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"
        target_content = "converted audio content"
        target_file.write_text(target_content)

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        file_service._handle_successful_conversion(source_file, target_file, job)

        # Target should remain unchanged
        assert target_file.exists()
        assert target_file.read_text() == target_content

    def test_handle_successful_conversion_with_large_target_file(
        self, file_service, temp_dirs
    ):
        """Test handling with large target file."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"
        # Create a larger target file
        target_file.write_bytes(b"x" * 10000)

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        assert result.status == "completed"
        assert target_file.stat().st_size == 10000

    def test_handle_successful_conversion_in_nested_directory(
        self, file_service, temp_dirs
    ):
        """Test successful conversion in nested directory structure."""
        source_dir, target_dir = temp_dirs

        source_subdir = source_dir / "playlist" / "subfolder"
        source_subdir.mkdir(parents=True)
        source_file = source_subdir / "track.m4a"
        source_file.write_text("audio")

        target_subdir = target_dir / "playlist" / "subfolder"
        target_subdir.mkdir(parents=True)
        target_file = target_subdir / "track.mp3"
        target_file.write_text("converted")

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        assert result.status == "completed"
        assert source_file.stat().st_size == 0

    def test_handle_successful_conversion_preserves_job_data(
        self, file_service, temp_dirs
    ):
        """Test that successful conversion preserves original job data."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.flac"
        target_file.write_text("converted")

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".flac",
            quality="7",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        # Original job data should be preserved
        assert result.source_path == source_file
        assert result.target_path == target_file
        assert result.source_format == ".m4a"
        assert result.target_format == ".flac"
        assert result.quality == "7"

    def test_handle_successful_conversion_returns_same_job_object(
        self, file_service, temp_dirs
    ):
        """Test that method modifies and returns the same job object."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"
        target_file.write_text("converted")

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        # Should return the same object (modified in place)
        assert result is job

    def test_handle_successful_conversion_with_special_characters_in_path(
        self, file_service, temp_dirs
    ):
        """Test handling with special characters in file paths."""
        source_dir, target_dir = temp_dirs

        # Create file with special characters
        source_file = source_dir / "audio with spaces & symbols.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio with spaces & symbols.mp3"
        target_file.write_text("converted")

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        assert result.status == "completed"
        assert source_file.stat().st_size == 0

    def test_handle_successful_conversion_does_not_log_on_failure(
        self, file_service, temp_dirs, caplog
    ):
        """Test that failure case doesn't log success message."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"  # Not created

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        file_service._handle_successful_conversion(source_file, target_file, job)

        # Should not log success when target doesn't exist
        assert "Successfully converted" not in caplog.text

    def test_handle_successful_conversion_with_empty_target_file(
        self, file_service, temp_dirs
    ):
        """Test handling when target file is empty (but exists)."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"
        target_file.touch()  # Create empty target

        job = ConversionJob(
            source_path=source_file,
            target_path=target_file,
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        result = file_service._handle_successful_conversion(
            source_file, target_file, job
        )

        # Empty target still counts as success
        assert result.status == "completed"
        assert target_file.exists()
        assert source_file.stat().st_size == 0

    def test_handle_conversion_error_subprocess_error(self, file_service):
        """Test handling of subprocess.CalledProcessError."""
        import subprocess  # nosec B404

        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = subprocess.CalledProcessError(
            1, "ffmpeg", stderr="FFmpeg error message"
        )

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert "ffmpeg error: FFmpeg error message" in result.error_message

    def test_handle_conversion_error_generic_exception(self, file_service):
        """Test handling of generic exception."""
        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = ValueError("Something went wrong")

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert result.error_message == "Something went wrong"

    def test_handle_conversion_error_with_stderr_output(self, file_service, caplog):
        """Test error handling includes stderr output from subprocess."""
        import logging
        import subprocess  # nosec B404

        caplog.set_level(logging.ERROR)

        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        stderr_output = "Error: Invalid codec\nFFmpeg failed"
        error = subprocess.CalledProcessError(1, "ffmpeg", stderr=stderr_output)

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert "ffmpeg error:" in result.error_message
        assert stderr_output in result.error_message
        assert "ffmpeg conversion failed" in caplog.text

    def test_handle_conversion_error_with_empty_stderr(self, file_service):
        """Test error handling when subprocess has empty stderr."""
        import subprocess  # nosec B404

        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = subprocess.CalledProcessError(1, "ffmpeg", stderr="")

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert result.error_message == "ffmpeg error: "

    def test_handle_conversion_error_with_none_stderr(self, file_service):
        """Test error handling when subprocess has None stderr."""
        import subprocess  # nosec B404

        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = subprocess.CalledProcessError(1, "ffmpeg", stderr=None)

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert "ffmpeg error:" in result.error_message

    def test_handle_conversion_error_with_oserror(self, file_service, caplog):
        """Test error handling for OSError exceptions."""
        import logging

        caplog.set_level(logging.ERROR)

        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = OSError("Permission denied")

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert result.error_message == "Permission denied"
        assert "Conversion failed" in caplog.text

    def test_handle_conversion_error_with_ioerror(self, file_service):
        """Test error handling for IOError exceptions."""
        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = IOError("Disk full")

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert result.error_message == "Disk full"

    def test_handle_conversion_error_with_keyboard_interrupt(self, file_service):
        """Test error handling for KeyboardInterrupt."""
        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = KeyboardInterrupt()

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert result.error_message == ""

    def test_handle_conversion_error_preserves_job_data(self, file_service):
        """Test that error handling preserves original job data."""
        import subprocess  # nosec B404

        source_path = Path("/path/to/source.m4a")
        target_path = Path("/path/to/target.mp3")

        job = ConversionJob(
            source_path=source_path,
            target_path=target_path,
            source_format=".m4a",
            target_format=".mp3",
            quality="5",
        )

        error = subprocess.CalledProcessError(1, "ffmpeg", stderr="Error")

        result = file_service._handle_conversion_error(error, job)

        # Job data should be preserved
        assert result.source_path == source_path
        assert result.target_path == target_path
        assert result.source_format == ".m4a"
        assert result.target_format == ".mp3"
        assert result.quality == "5"
        assert result.status == "failed"

    def test_handle_conversion_error_with_unicode_characters(self, file_service):
        """Test error handling with unicode characters in error message."""
        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = ValueError("Error with unicode: 日本語 émojis 🎵")

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert "日本語" in result.error_message
        assert "émojis" in result.error_message
        assert "🎵" in result.error_message

    def test_handle_conversion_error_with_multiline_stderr(self, file_service):
        """Test error handling with multiline stderr output."""
        import subprocess  # nosec B404

        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        stderr = """FFmpeg error on line 1
Error: Invalid codec
Stack trace:
  at function1()
  at function2()"""

        error = subprocess.CalledProcessError(1, "ffmpeg", stderr=stderr)

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert "FFmpeg error on line 1" in result.error_message
        assert "Stack trace:" in result.error_message

    def test_handle_conversion_error_logs_different_error_types(
        self, file_service, caplog
    ):
        """Test that different error types are logged correctly."""
        import logging
        import subprocess  # nosec B404

        caplog.set_level(logging.ERROR)

        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        # Test CalledProcessError logging
        caplog.clear()
        error1 = subprocess.CalledProcessError(1, "ffmpeg", stderr="FFmpeg error")
        file_service._handle_conversion_error(error1, job)
        assert "ffmpeg conversion failed" in caplog.text

        # Test generic exception logging
        caplog.clear()
        error2 = RuntimeError("Runtime error")
        file_service._handle_conversion_error(error2, job)
        assert "Conversion failed" in caplog.text

    def test_handle_conversion_error_with_file_not_found(self, file_service):
        """Test error handling for FileNotFoundError."""
        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = FileNotFoundError("FFmpeg not found in PATH")

        result = file_service._handle_conversion_error(error, job)

        assert result.status == "failed"
        assert "FFmpeg not found in PATH" in result.error_message

    def test_handle_conversion_error_returns_same_job_object(self, file_service):
        """Test that error handling modifies and returns the same job object."""
        job = ConversionJob(
            source_path=Path("source.m4a"),
            target_path=Path("target.mp3"),
            source_format=".m4a",
            target_format=".mp3",
            quality="2",
        )

        error = ValueError("Error")

        result = file_service._handle_conversion_error(error, job)

        # Should return the same object (modified in place)
        assert result is job

    def test_convert_audio_with_empty_file(self, file_service, temp_dirs, caplog):
        """Test convert_audio skips empty files."""
        import logging

        caplog.set_level(logging.WARNING)

        source_dir, target_dir = temp_dirs

        # Create empty source file
        source_file = source_dir / "empty.m4a"
        source_file.touch()
        target_file = target_dir / "empty.mp3"

        result = file_service.convert_audio(source_file, target_file, "2")

        assert result.status == "completed"
        assert result.was_skipped is True
        assert "Skipping conversion of empty file" in caplog.text

    def test_convert_audio_creates_target_directory(self, file_service, temp_dirs):
        """Test that convert_audio creates target directory if needed."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")

        # Target in nested directory that doesn't exist
        target_file = target_dir / "subdir1" / "subdir2" / "audio.mp3"

        with patch.object(file_service, "_run_ffmpeg_conversion"), patch.object(
            file_service, "_handle_successful_conversion"
        ) as mock:
            mock.return_value = ConversionJob(
                source_path=source_file,
                target_path=target_file,
                source_format=".m4a",
                target_format=".mp3",
                quality="2",
                status="completed",
            )

            file_service.convert_audio(source_file, target_file, "2")

        # Verify directory was created
        assert target_file.parent.exists()
        assert target_file.parent.is_dir()

    def test_convert_audio_validates_paths(self, file_service, temp_dirs):
        """Test that convert_audio validates paths."""
        from tidal_cleanup.legacy.file_service import FileOperationError

        source_dir, target_dir = temp_dirs

        # Non-existent source file
        source_file = source_dir / "nonexistent.m4a"
        target_file = target_dir / "audio.mp3"

        with pytest.raises(FileOperationError, match="Source file does not exist"):
            file_service.convert_audio(source_file, target_file, "2")

    def test_convert_audio_validates_quality(self, file_service, temp_dirs):
        """Test that convert_audio validates quality parameter."""
        from tidal_cleanup.legacy.file_service import FileOperationError

        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio")
        target_file = target_dir / "audio.mp3"

        with pytest.raises(FileOperationError, match="Quality must be 0-9"):
            file_service.convert_audio(source_file, target_file, "15")

    def test_convert_audio_sets_job_to_processing(
        self, file_service, temp_dirs, caplog
    ):
        """Test that job status is set to processing during conversion."""
        import logging

        caplog.set_level(logging.INFO)

        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"

        with patch.object(file_service, "_run_ffmpeg_conversion") as mock_ffmpeg:
            # Simulate successful conversion
            def create_target(*args, **kwargs):
                target_file.write_text("converted")

            mock_ffmpeg.side_effect = create_target

            result = file_service.convert_audio(source_file, target_file, "2")

        assert result.status == "completed"
        assert f"Converting {source_file}" in caplog.text

    def test_convert_audio_calls_ffmpeg_conversion(self, file_service, temp_dirs):
        """Test that convert_audio calls FFmpeg conversion method."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"

        with patch.object(file_service, "_run_ffmpeg_conversion") as mock_ffmpeg:
            # Simulate successful conversion
            def create_target(*args, **kwargs):
                target_file.write_text("converted")

            mock_ffmpeg.side_effect = create_target

            file_service.convert_audio(source_file, target_file, "2")

        # Verify FFmpeg was called
        mock_ffmpeg.assert_called_once_with(source_file, target_file, "2")

    def test_convert_audio_handles_ffmpeg_failure(self, file_service, temp_dirs):
        """Test handling of FFmpeg conversion failure."""
        import subprocess  # nosec B404

        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"

        with patch.object(file_service, "_run_ffmpeg_conversion") as mock_ffmpeg:
            mock_ffmpeg.side_effect = subprocess.CalledProcessError(
                1, "ffmpeg", stderr="Conversion failed"
            )

            result = file_service.convert_audio(source_file, target_file, "2")

        assert result.status == "failed"
        assert "ffmpeg error" in result.error_message

    def test_convert_audio_returns_correct_job_structure(self, file_service, temp_dirs):
        """Test that convert_audio returns properly structured ConversionJob."""
        source_dir, target_dir = temp_dirs

        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.mp3"

        with patch.object(file_service, "_run_ffmpeg_conversion") as mock_ffmpeg:
            # Simulate successful conversion
            def create_target(*args, **kwargs):
                target_file.write_text("converted")

            mock_ffmpeg.side_effect = create_target

            result = file_service.convert_audio(source_file, target_file, "5")

        assert isinstance(result, ConversionJob)
        assert result.source_path == source_file
        assert result.target_path == target_file
        assert result.source_format == ".m4a"
        assert result.target_format == ".mp3"
        assert result.quality == "5"
        assert result.status == "completed"

    def test_convert_audio_with_different_formats(self, file_service, temp_dirs):
        """Test conversion between different audio formats."""
        source_dir, target_dir = temp_dirs

        # Test m4a to flac
        source_file = source_dir / "audio.m4a"
        source_file.write_text("audio data")
        target_file = target_dir / "audio.flac"

        with patch.object(file_service, "_run_ffmpeg_conversion") as mock_ffmpeg:

            def create_target(*args, **kwargs):
                target_file.write_text("converted")

            mock_ffmpeg.side_effect = create_target

            result = file_service.convert_audio(source_file, target_file, "2")

        assert result.source_format == ".m4a"
        assert result.target_format == ".flac"
        assert result.status == "completed"
