"""Tests for the DirectoryDiffService."""

import tempfile
from pathlib import Path

import pytest

from tidal_cleanup.services.directory_diff_service import (
    DirectoryDiff,
    DirectoryDiffService,
    FileIdentity,
)


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with (
        tempfile.TemporaryDirectory() as source_dir,
        tempfile.TemporaryDirectory() as target_dir,
    ):
        yield Path(source_dir), Path(target_dir)


@pytest.fixture
def diff_service():
    """Create a DirectoryDiffService instance."""
    return DirectoryDiffService()


def test_compare_empty_directories(diff_service, temp_dirs):
    """Test comparing two empty directories."""
    source_dir, target_dir = temp_dirs

    diff = diff_service.compare_directories(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    assert len(diff.only_in_source) == 0
    assert len(diff.only_in_target) == 0
    assert len(diff.in_both) == 0


def test_compare_only_in_source(diff_service, temp_dirs):
    """Test files that exist only in source directory."""
    source_dir, target_dir = temp_dirs

    # Create files in source directory
    (source_dir / "track1.m4a").touch()
    (source_dir / "track2.m4a").touch()

    diff = diff_service.compare_directories(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    assert len(diff.only_in_source) == 2
    assert "track1" in diff.only_in_source
    assert "track2" in diff.only_in_source
    assert len(diff.only_in_target) == 0
    assert len(diff.in_both) == 0


def test_compare_only_in_target(diff_service, temp_dirs):
    """Test files that exist only in target directory."""
    source_dir, target_dir = temp_dirs

    # Create files in target directory
    (target_dir / "track1.mp3").touch()
    (target_dir / "track2.mp3").touch()

    diff = diff_service.compare_directories(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    assert len(diff.only_in_source) == 0
    assert len(diff.only_in_target) == 2
    assert "track1" in diff.only_in_target
    assert "track2" in diff.only_in_target
    assert len(diff.in_both) == 0


def test_compare_in_both(diff_service, temp_dirs):
    """Test files that exist in both directories."""
    source_dir, target_dir = temp_dirs

    # Create matching files
    (source_dir / "track1.m4a").touch()
    (source_dir / "track2.m4a").touch()
    (target_dir / "track1.mp3").touch()
    (target_dir / "track2.mp3").touch()

    diff = diff_service.compare_directories(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    assert len(diff.only_in_source) == 0
    assert len(diff.only_in_target) == 0
    assert len(diff.in_both) == 2
    assert "track1" in diff.in_both
    assert "track2" in diff.in_both


def test_compare_mixed_scenario(diff_service, temp_dirs):
    """Test a realistic mixed scenario."""
    source_dir, target_dir = temp_dirs

    # Create files in source (need conversion)
    (source_dir / "new_track.m4a").touch()
    (source_dir / "another_new.m4a").touch()

    # Create matching files (already converted)
    (source_dir / "existing1.m4a").touch()
    (source_dir / "existing2.m4a").touch()
    (target_dir / "existing1.mp3").touch()
    (target_dir / "existing2.mp3").touch()

    # Create orphaned files in target (need deletion)
    (target_dir / "orphaned1.mp3").touch()
    (target_dir / "orphaned2.mp3").touch()

    diff = diff_service.compare_directories(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    # Verify counts
    assert len(diff.only_in_source) == 2  # new_track, another_new
    assert len(diff.only_in_target) == 2  # orphaned1, orphaned2
    assert len(diff.in_both) == 2  # existing1, existing2

    # Verify specific files
    assert "new_track" in diff.only_in_source
    assert "another_new" in diff.only_in_source
    assert "orphaned1" in diff.only_in_target
    assert "orphaned2" in diff.only_in_target
    assert "existing1" in diff.in_both
    assert "existing2" in diff.in_both


def test_compare_with_subdirectories(diff_service, temp_dirs):
    """Test comparing directories with subdirectories."""
    source_dir, target_dir = temp_dirs

    # Create subdirectories
    (source_dir / "subdir1").mkdir()
    (source_dir / "subdir2").mkdir()
    (target_dir / "subdir1").mkdir()
    (target_dir / "subdir2").mkdir()

    # Create files in subdirectories
    (source_dir / "subdir1" / "track1.m4a").touch()
    (source_dir / "subdir2" / "track2.m4a").touch()
    (target_dir / "subdir1" / "track1.mp3").touch()
    (target_dir / "subdir2" / "track3.mp3").touch()

    diff = diff_service.compare_directories(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    assert len(diff.only_in_source) == 1  # track2
    assert len(diff.only_in_target) == 1  # track3
    assert len(diff.in_both) == 1  # track1


def test_compare_by_stem_with_extension_mapping(diff_service, temp_dirs):
    """Test the convenience method for stem-based comparison."""
    source_dir, target_dir = temp_dirs

    # Create test files
    (source_dir / "track1.m4a").touch()
    (target_dir / "track1.mp3").touch()
    (source_dir / "track2.m4a").touch()

    diff = diff_service.compare_by_stem_with_extension_mapping(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    assert len(diff.only_in_source) == 1  # track2
    assert len(diff.only_in_target) == 0
    assert len(diff.in_both) == 1  # track1


def test_custom_identity_function(diff_service, temp_dirs):
    """Test using a custom identity function."""
    source_dir, target_dir = temp_dirs

    # Create files with different naming patterns
    (source_dir / "Artist - Track1.m4a").touch()
    (target_dir / "Artist - Track1.mp3").touch()

    # Custom identity function that normalizes names
    def custom_identity(path: Path) -> str:
        return path.stem.lower().replace(" ", "")

    diff = diff_service.compare_directories(
        source_dir,
        target_dir,
        source_extensions=(".m4a",),
        target_extensions=(".mp3",),
        identity_fn=custom_identity,
    )

    assert len(diff.in_both) == 1


def test_file_identity_paths(diff_service, temp_dirs):
    """Test that FileIdentity objects contain correct paths."""
    source_dir, target_dir = temp_dirs

    (source_dir / "track1.m4a").touch()
    (target_dir / "track2.mp3").touch()

    diff = diff_service.compare_directories(
        source_dir, target_dir, source_extensions=(".m4a",), target_extensions=(".mp3",)
    )

    # Check source identity
    source_identity = diff.source_identities["track1"]
    assert isinstance(source_identity, FileIdentity)
    assert source_identity.key == "track1"
    assert source_identity.path.name == "track1.m4a"
    assert source_identity.path.is_absolute()

    # Check target identity
    target_identity = diff.target_identities["track2"]
    assert isinstance(target_identity, FileIdentity)
    assert target_identity.key == "track2"
    assert target_identity.path.name == "track2.mp3"
    assert target_identity.path.is_absolute()


def test_multiple_source_extensions(diff_service, temp_dirs):
    """Test handling multiple source file extensions."""
    source_dir, target_dir = temp_dirs

    # Create files with different extensions
    (source_dir / "track1.m4a").touch()
    (source_dir / "track2.mp4").touch()
    (target_dir / "track1.mp3").touch()

    diff = diff_service.compare_directories(
        source_dir,
        target_dir,
        source_extensions=(".m4a", ".mp4"),
        target_extensions=(".mp3",),
    )

    assert len(diff.only_in_source) == 1  # track2
    assert len(diff.only_in_target) == 0
    assert len(diff.in_both) == 1  # track1


def test_nonexistent_directory_handling(diff_service):
    """Test handling of non-existent directories."""
    nonexistent_source = Path("/nonexistent/source")
    nonexistent_target = Path("/nonexistent/target")

    diff = diff_service.compare_directories(
        nonexistent_source,
        nonexistent_target,
        source_extensions=(".m4a",),
        target_extensions=(".mp3",),
    )

    assert len(diff.only_in_source) == 0
    assert len(diff.only_in_target) == 0
    assert len(diff.in_both) == 0


def test_directory_diff_repr():
    """Test the string representation of DirectoryDiff."""
    diff = DirectoryDiff(
        only_in_source={"file1", "file2"},
        only_in_target={"file3"},
        in_both={"file4", "file5", "file6"},
        source_identities={},
        target_identities={},
    )

    repr_str = repr(diff)
    assert "to_add=2" in repr_str
    assert "to_remove=1" in repr_str
    assert "existing=3" in repr_str
