"""Tests for conflict resolver."""

import os
from pathlib import Path

import pytest

from src.tidal_cleanup.database.conflict_resolver import (
    Conflict,
    ConflictResolution,
    ConflictResolutionResult,
    ConflictResolver,
    ConflictType,
)
from src.tidal_cleanup.database.service import DatabaseService
from src.tidal_cleanup.database.sync_decision_engine import (
    DecisionResult,
    SyncAction,
)


@pytest.fixture
def db_service(tmp_path):
    """Create a temporary database service."""
    db_path = tmp_path / "test.db"
    return DatabaseService(db_path)


@pytest.fixture
def resolver(db_service):
    """Create a conflict resolver."""
    return ConflictResolver(
        db_service=db_service,
        auto_resolve=True,
        backup_conflicts=True,
        max_retries=3,
    )


@pytest.fixture
def test_file(tmp_path):
    """Create a test file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    return file_path


class TestConflict:
    """Test Conflict dataclass."""

    def test_conflict_str_basic(self):
        """Test basic conflict string representation."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test conflict",
        )
        assert "file_exists: Test conflict" in str(conflict)

    def test_conflict_str_with_file(self):
        """Test conflict string with file path."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_MISSING,
            description="File not found",
            file_path=Path("/test/file.txt"),
        )
        result = str(conflict)
        assert "file_missing: File not found" in result
        assert "(file: /test/file.txt)" in result

    def test_conflict_str_with_resolution(self):
        """Test conflict string with resolution."""
        conflict = Conflict(
            conflict_type=ConflictType.PERMISSION_DENIED,
            description="Cannot access",
            resolution=ConflictResolution.SKIP,
        )
        result = str(conflict)
        assert "permission_denied: Cannot access" in result
        assert "[resolved: skip]" in result

    def test_conflict_str_full(self):
        """Test conflict string with all fields."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Already exists",
            file_path=Path("/test/file.txt"),
            resolution=ConflictResolution.OVERWRITE,
        )
        result = str(conflict)
        assert "file_exists: Already exists" in result
        assert "(file: /test/file.txt)" in result
        assert "[resolved: overwrite]" in result


class TestConflictResolutionResult:
    """Test ConflictResolutionResult dataclass."""

    def test_add_conflict_resolved(self):
        """Test adding a resolved conflict."""
        result = ConflictResolutionResult()
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
            resolution=ConflictResolution.OVERWRITE,
        )

        result.add_conflict(conflict)

        assert result.conflicts_detected == 1
        assert result.conflicts_resolved == 1
        assert result.conflicts_skipped == 0
        assert result.conflicts_failed == 0
        assert len(result.conflicts) == 1

    def test_add_conflict_skipped(self):
        """Test adding a skipped conflict."""
        result = ConflictResolutionResult()
        conflict = Conflict(
            conflict_type=ConflictType.PERMISSION_DENIED,
            description="Test",
            resolution=ConflictResolution.SKIP,
        )

        result.add_conflict(conflict)

        assert result.conflicts_detected == 1
        assert result.conflicts_resolved == 0
        assert result.conflicts_skipped == 1
        assert result.conflicts_failed == 0

    def test_add_conflict_failed(self):
        """Test adding a failed conflict."""
        result = ConflictResolutionResult()
        conflict = Conflict(
            conflict_type=ConflictType.CONCURRENT_MODIFICATION,
            description="Test",
            resolution=None,  # No resolution = failed
        )

        result.add_conflict(conflict)

        assert result.conflicts_detected == 1
        assert result.conflicts_resolved == 0
        assert result.conflicts_skipped == 0
        assert result.conflicts_failed == 1


class TestConflictResolverInit:
    """Test ConflictResolver initialization."""

    def test_init_default(self, db_service):
        """Test initialization with defaults."""
        resolver = ConflictResolver(db_service)

        assert resolver.db_service == db_service
        assert resolver.auto_resolve is True
        assert resolver.backup_conflicts is True
        assert resolver.max_retries == 3

    def test_init_custom(self, db_service):
        """Test initialization with custom parameters."""
        resolver = ConflictResolver(
            db_service=db_service,
            auto_resolve=False,
            backup_conflicts=False,
            max_retries=5,
        )

        assert resolver.auto_resolve is False
        assert resolver.backup_conflicts is False
        assert resolver.max_retries == 5


class TestCheckFileConflicts:
    """Test check_file_conflicts method."""

    def test_no_conflict_download_new_file(self, resolver, tmp_path):
        """Test no conflict when downloading to new location."""
        target_path = tmp_path / "new_file.txt"
        conflict = resolver.check_file_conflicts(target_path, SyncAction.DOWNLOAD_TRACK)

        assert conflict is None

    def test_conflict_file_exists(self, resolver, test_file):
        """Test conflict when file already exists."""
        conflict = resolver.check_file_conflicts(test_file, SyncAction.DOWNLOAD_TRACK)

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.FILE_EXISTS
        assert conflict.file_path == test_file
        assert "File already exists" in conflict.description

    def test_conflict_symlink_exists(self, resolver, tmp_path):
        """Test conflict when symlink already exists."""
        source = tmp_path / "source.txt"
        source.write_text("content")
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(source)

        conflict = resolver.check_file_conflicts(symlink, SyncAction.DOWNLOAD_TRACK)

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.FILE_EXISTS
        assert "Symlink already exists" in conflict.description

    def test_conflict_broken_symlink(self, resolver, tmp_path):
        """Test conflict when symlink target doesn't exist."""
        source = tmp_path / "missing.txt"
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(source)

        conflict = resolver.check_file_conflicts(symlink, SyncAction.CREATE_SYMLINK)

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.SYMLINK_BROKEN
        assert "Symlink target does not exist" in conflict.description

    def test_conflict_broken_symlink_update(self, resolver, tmp_path):
        """Test conflict for broken symlink with UPDATE action."""
        source = tmp_path / "missing.txt"
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(source)

        conflict = resolver.check_file_conflicts(symlink, SyncAction.UPDATE_SYMLINK)

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.SYMLINK_BROKEN


class TestResolveFileConflict:
    """Test resolve_file_conflict method."""

    def test_no_auto_resolve(self, db_service):
        """Test resolution when auto_resolve is False."""
        resolver = ConflictResolver(db_service, auto_resolve=False)
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.SKIP

    def test_resolve_file_exists_with_backup(self, resolver):
        """Test resolving FILE_EXISTS with backup enabled."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.BACKUP

    def test_resolve_file_exists_no_backup(self, db_service):
        """Test resolving FILE_EXISTS without backup."""
        resolver = ConflictResolver(db_service, backup_conflicts=False)
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.OVERWRITE

    def test_resolve_file_missing(self, resolver):
        """Test resolving FILE_MISSING."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_MISSING,
            description="Test",
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.RETRY

    def test_resolve_symlink_broken(self, resolver):
        """Test resolving SYMLINK_BROKEN."""
        conflict = Conflict(
            conflict_type=ConflictType.SYMLINK_BROKEN,
            description="Test",
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.OVERWRITE

    def test_resolve_permission_denied(self, resolver):
        """Test resolving PERMISSION_DENIED."""
        conflict = Conflict(
            conflict_type=ConflictType.PERMISSION_DENIED,
            description="Test",
            file_path=Path("/test/file.txt"),
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.SKIP

    def test_resolve_concurrent_modification(self, resolver):
        """Test resolving CONCURRENT_MODIFICATION."""
        conflict = Conflict(
            conflict_type=ConflictType.CONCURRENT_MODIFICATION,
            description="Test",
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.RETRY

    def test_resolve_unknown_type(self, resolver):
        """Test resolving unknown conflict type defaults to SKIP."""
        conflict = Conflict(
            conflict_type=ConflictType.LOCK_TIMEOUT,
            description="Test",
        )

        resolution = resolver.resolve_file_conflict(conflict)

        assert resolution == ConflictResolution.SKIP


class TestDetectDecisionConflicts:
    """Test detect_decision_conflicts method."""

    def test_no_conflicts(self, resolver):
        """Test detecting conflicts with no conflicts."""
        decisions = [
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                playlist_id=1,
                track_id=1,
                target_path="/path/file1.mp3",
            ),
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                playlist_id=1,
                track_id=2,
                target_path="/path/file2.mp3",
            ),
        ]

        conflicts = resolver.detect_decision_conflicts(decisions)

        assert len(conflicts) == 0

    def test_duplicate_decision(self, resolver):
        """Test detecting duplicate decisions."""
        decisions = [
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                playlist_id=1,
                track_id=1,
                target_path="/path/file.mp3",
            ),
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                playlist_id=1,
                track_id=1,
                target_path="/path/file.mp3",
            ),
        ]

        conflicts = resolver.detect_decision_conflicts(decisions)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.DUPLICATE_DECISION
        assert "2 times" in conflicts[0].description

    def test_conflicting_actions(self, resolver):
        """Test detecting conflicting actions."""
        decisions = [
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                playlist_id=1,
                track_id=1,
                target_path="/path/file.mp3",
            ),
            DecisionResult(
                action=SyncAction.CREATE_SYMLINK,
                playlist_id=1,
                track_id=1,
                target_path="/path/file.mp3",
            ),
        ]

        conflicts = resolver.detect_decision_conflicts(decisions)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.CONFLICTING_ACTIONS
        assert "Multiple conflicting actions" in conflicts[0].description

    def test_decisions_without_target_path(self, resolver):
        """Test decisions without target paths are ignored."""
        decisions = [
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                playlist_id=1,
                track_id=1,
                target_path=None,
            ),
        ]

        conflicts = resolver.detect_decision_conflicts(decisions)

        assert len(conflicts) == 0


class TestResolveDecisionConflicts:
    """Test resolve_decision_conflicts method."""

    def test_resolve_duplicate_decision(self, resolver):
        """Test resolving duplicate decisions."""
        decision1 = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            playlist_id=1,
            track_id=1,
            target_path="/path/file.mp3",
        )
        decision2 = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            playlist_id=1,
            track_id=1,
            target_path="/path/file.mp3",
        )

        conflict = Conflict(
            conflict_type=ConflictType.DUPLICATE_DECISION,
            description="Duplicate",
            metadata={"decisions": [decision1, decision2]},
        )

        resolved = resolver.resolve_decision_conflicts([conflict])

        assert len(resolved) == 1
        assert resolved[0] == decision1
        assert conflict.resolution == ConflictResolution.USE_EXISTING

    def test_resolve_conflicting_actions(self, resolver):
        """Test resolving conflicting actions prioritizes DOWNLOAD."""
        decision1 = DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            playlist_id=1,
            track_id=1,
            target_path="/path/file.mp3",
        )
        decision2 = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            playlist_id=1,
            track_id=1,
            target_path="/path/file.mp3",
        )
        decision3 = DecisionResult(
            action=SyncAction.UPDATE_SYMLINK,
            playlist_id=1,
            track_id=1,
            target_path="/path/file.mp3",
        )

        conflict = Conflict(
            conflict_type=ConflictType.CONFLICTING_ACTIONS,
            description="Conflicting",
            metadata={"decisions": [decision1, decision2, decision3]},
        )

        resolved = resolver.resolve_decision_conflicts([conflict])

        assert len(resolved) == 1
        assert resolved[0].action == SyncAction.DOWNLOAD_TRACK
        assert conflict.resolution == ConflictResolution.USE_EXISTING

    def test_resolve_empty_decisions(self, resolver):
        """Test resolving conflict with no decisions."""
        conflict = Conflict(
            conflict_type=ConflictType.DUPLICATE_DECISION,
            description="Empty",
            metadata={"decisions": []},
        )

        resolved = resolver.resolve_decision_conflicts([conflict])

        assert len(resolved) == 0

    def test_resolve_unknown_conflict_type(self, resolver):
        """Test resolving unknown conflict type returns empty list."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Unknown",
        )

        resolved = resolver.resolve_decision_conflicts([conflict])

        assert len(resolved) == 0


class TestBackupFile:
    """Test backup_file method."""

    def test_backup_regular_file(self, resolver, test_file):
        """Test backing up a regular file."""
        backup_path = resolver.backup_file(test_file)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_text() == "test content"
        assert ".backup_" in backup_path.name

    def test_backup_symlink(self, resolver, tmp_path):
        """Test backing up a symlink."""
        source = tmp_path / "source.txt"
        source.write_text("content")
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(source)

        backup_path = resolver.backup_file(symlink)

        assert backup_path is not None
        assert backup_path.is_symlink()
        assert os.readlink(backup_path) == str(source)

    def test_backup_missing_file(self, resolver, tmp_path):
        """Test backing up a file that doesn't exist."""
        missing_file = tmp_path / "missing.txt"
        backup_path = resolver.backup_file(missing_file)

        assert backup_path is None

    def test_backup_failure(self, resolver, test_file, monkeypatch):
        """Test backup failure handling."""
        # Mock shutil.copy2 to raise an exception
        import shutil

        original_copy2 = shutil.copy2

        def mock_copy2(*args, **kwargs):
            raise OSError("Backup failed")

        monkeypatch.setattr(shutil, "copy2", mock_copy2)

        backup_path = resolver.backup_file(test_file)

        assert backup_path is None

        # Restore original
        monkeypatch.setattr(shutil, "copy2", original_copy2)


class TestApplyResolution:
    """Test apply_resolution method."""

    def test_apply_backup_resolution(self, resolver, test_file):
        """Test applying BACKUP resolution."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
            file_path=test_file,
        )

        success = resolver.apply_resolution(conflict, ConflictResolution.BACKUP)

        assert success is True
        assert conflict.resolution == ConflictResolution.BACKUP
        assert "backup_path" in conflict.metadata

    def test_apply_backup_failure(self, resolver, tmp_path):
        """Test applying BACKUP when file doesn't exist."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
            file_path=tmp_path / "missing.txt",
        )

        success = resolver.apply_resolution(conflict, ConflictResolution.BACKUP)

        assert success is False

    def test_apply_overwrite_resolution(self, resolver, test_file):
        """Test applying OVERWRITE resolution."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
            file_path=test_file,
        )

        success = resolver.apply_resolution(conflict, ConflictResolution.OVERWRITE)

        assert success is True
        assert not test_file.exists()
        assert conflict.resolution == ConflictResolution.OVERWRITE

    def test_apply_overwrite_missing_file(self, resolver, tmp_path):
        """Test applying OVERWRITE when file doesn't exist."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
            file_path=tmp_path / "missing.txt",
        )

        success = resolver.apply_resolution(conflict, ConflictResolution.OVERWRITE)

        assert success is True

    def test_apply_skip_resolution(self, resolver):
        """Test applying SKIP resolution."""
        conflict = Conflict(
            conflict_type=ConflictType.PERMISSION_DENIED,
            description="Test",
        )

        success = resolver.apply_resolution(conflict, ConflictResolution.SKIP)

        assert success is True
        assert conflict.resolution == ConflictResolution.SKIP

    def test_apply_other_resolution(self, resolver):
        """Test applying other resolutions returns True."""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_MISSING,
            description="Test",
        )

        success = resolver.apply_resolution(conflict, ConflictResolution.RETRY)

        assert success is True

    def test_apply_resolution_exception(self, resolver, test_file, monkeypatch):
        """Test handling exceptions during resolution."""
        import os

        original_unlink = os.unlink

        def mock_unlink(path, *args, **kwargs):
            if str(path) == str(test_file):
                raise OSError("Delete failed")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", mock_unlink)

        conflict = Conflict(
            conflict_type=ConflictType.FILE_EXISTS,
            description="Test",
            file_path=test_file,
        )

        success = resolver.apply_resolution(conflict, ConflictResolution.OVERWRITE)

        assert success is False
