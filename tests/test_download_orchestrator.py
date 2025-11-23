"""Tests for download orchestrator."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from tidal_cleanup.database.deduplication_logic import DeduplicationLogic
from tidal_cleanup.database.download_orchestrator import (
    DownloadOrchestrator,
    ExecutionResult,
)
from tidal_cleanup.database.models import DownloadStatus, Playlist, PlaylistTrack, Track
from tidal_cleanup.database.service import DatabaseService
from tidal_cleanup.database.sync_decision_engine import (
    DecisionResult,
    SyncAction,
    SyncDecisions,
)


@pytest.fixture
def mock_db_service():
    """Create a mock database service."""
    service = MagicMock(spec=DatabaseService)
    service.get_session.return_value.__enter__ = Mock()
    service.get_session.return_value.__exit__ = Mock(return_value=False)
    return service


@pytest.fixture
def temp_music_root(tmp_path):
    """Create a temporary music root directory."""
    music_root = tmp_path / "Music"
    music_root.mkdir()
    (music_root / "Playlists").mkdir()
    return music_root


@pytest.fixture
def orchestrator(mock_db_service, temp_music_root):
    """Create a DownloadOrchestrator instance."""
    return DownloadOrchestrator(
        db_service=mock_db_service,
        music_root=temp_music_root,
        dry_run=False,
    )


@pytest.fixture
def dry_run_orchestrator(mock_db_service, temp_music_root):
    """Create a DownloadOrchestrator instance in dry-run mode."""
    return DownloadOrchestrator(
        db_service=mock_db_service,
        music_root=temp_music_root,
        dry_run=True,
    )


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_initialization(self):
        """Test ExecutionResult initialization with defaults."""
        result = ExecutionResult()
        assert result.decisions_executed == 0
        assert result.downloads_attempted == 0
        assert result.downloads_successful == 0
        assert result.downloads_failed == 0
        assert result.symlinks_created == 0
        assert result.symlinks_updated == 0
        assert result.symlinks_removed == 0
        assert result.files_removed == 0
        assert result.errors == []

    def test_add_error(self, caplog):
        """Test adding error messages."""
        result = ExecutionResult()
        result.add_error("Test error")
        assert len(result.errors) == 1
        assert result.errors[0] == "Test error"
        assert "Test error" in caplog.text

    def test_get_summary(self):
        """Test getting summary statistics."""
        result = ExecutionResult()
        result.decisions_executed = 5
        result.downloads_attempted = 3
        result.downloads_successful = 2
        result.downloads_failed = 1
        result.symlinks_created = 2
        result.errors = ["error1", "error2"]

        summary = result.get_summary()
        assert summary["decisions_executed"] == 5
        assert summary["downloads_attempted"] == 3
        assert summary["downloads_successful"] == 2
        assert summary["downloads_failed"] == 1
        assert summary["symlinks_created"] == 2
        assert summary["errors"] == 2


class TestDownloadOrchestratorInit:
    """Test DownloadOrchestrator initialization."""

    def test_init_with_defaults(self, mock_db_service, temp_music_root):
        """Test initialization with default parameters."""
        orch = DownloadOrchestrator(
            db_service=mock_db_service,
            music_root=temp_music_root,
        )
        assert orch.db_service == mock_db_service
        assert orch.music_root == temp_music_root
        assert orch.playlists_root == temp_music_root / "Playlists"
        assert isinstance(orch.dedup_logic, DeduplicationLogic)
        assert orch.dry_run is False

    def test_init_with_custom_dedup_logic(self, mock_db_service, temp_music_root):
        """Test initialization with custom deduplication logic."""
        custom_dedup = DeduplicationLogic(mock_db_service, strategy="largest_playlist")
        orch = DownloadOrchestrator(
            db_service=mock_db_service,
            music_root=temp_music_root,
            deduplication_logic=custom_dedup,
        )
        assert orch.dedup_logic == custom_dedup
        assert orch.dedup_logic.strategy == "largest_playlist"

    def test_init_with_dry_run(self, mock_db_service, temp_music_root):
        """Test initialization with dry_run enabled."""
        orch = DownloadOrchestrator(
            db_service=mock_db_service,
            music_root=temp_music_root,
            dry_run=True,
        )
        assert orch.dry_run is True

    def test_init_with_string_path(self, mock_db_service, temp_music_root):
        """Test initialization with string path instead of Path object."""
        orch = DownloadOrchestrator(
            db_service=mock_db_service,
            music_root=str(temp_music_root),
        )
        assert orch.music_root == temp_music_root
        assert isinstance(orch.music_root, Path)


class TestExecuteDecisions:
    """Test executing sync decisions."""

    def test_execute_empty_decisions(self, orchestrator):
        """Test executing empty decisions list."""
        decisions = SyncDecisions()
        result = orchestrator.execute_decisions(decisions)
        assert result.decisions_executed == 0
        assert len(result.errors) == 0

    def test_execute_multiple_decisions(self, orchestrator, temp_music_root):
        """Test executing multiple decisions with priority ordering."""
        decisions = SyncDecisions()

        # Add decisions with different priorities
        decisions.add_decision(
            DecisionResult(
                action=SyncAction.NO_ACTION,
                reason="Low priority",
                priority=1,
            )
        )
        decisions.add_decision(
            DecisionResult(
                action=SyncAction.NO_ACTION,
                reason="High priority",
                priority=10,
            )
        )
        decisions.add_decision(
            DecisionResult(
                action=SyncAction.NO_ACTION,
                reason="Medium priority",
                priority=5,
            )
        )

        result = orchestrator.execute_decisions(decisions)
        assert result.decisions_executed == 3
        assert len(result.errors) == 0

    def test_execute_with_error(self, orchestrator, mock_db_service):
        """Test handling errors during decision execution."""
        decisions = SyncDecisions()

        # Create a decision that will cause an error
        decisions.add_decision(
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                track_id=None,  # This will cause an error
                priority=5,
            )
        )

        result = orchestrator.execute_decisions(decisions)
        # Decision is executed even if it fails
        assert result.decisions_executed == 1
        assert result.downloads_attempted == 1
        assert result.downloads_failed == 1
        assert len(result.errors) == 1
        assert "track_id is None" in result.errors[0]


class TestExecuteDownload:
    """Test download execution."""

    def test_execute_download_success(self, orchestrator, mock_db_service):
        """Test successful download execution."""
        track = Track(id=1, tidal_id=123, title="Test Track")
        mock_db_service.get_track_by_id.return_value = track

        mock_session = MagicMock()
        mock_track_obj = MagicMock()
        mock_session.merge.return_value = mock_track_obj
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path="/path/to/track.flac",
            reason="Track not downloaded",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_download(decision, result)

        assert result.downloads_attempted == 1
        assert result.downloads_successful == 1
        assert result.downloads_failed == 0
        assert mock_track_obj.download_status == DownloadStatus.DOWNLOADING
        mock_session.commit.assert_called_once()

    def test_execute_download_none_track_id(self, orchestrator):
        """Test download execution with None track_id."""
        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=None,
            target_path="/path/to/track.flac",
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_download(decision, result)

        assert result.downloads_attempted == 1
        assert result.downloads_successful == 0
        assert result.downloads_failed == 1
        assert len(result.errors) == 1
        assert "track_id is None" in result.errors[0]

    def test_execute_download_track_not_found(self, orchestrator, mock_db_service):
        """Test download execution when track not found in database."""
        mock_db_service.get_track_by_id.return_value = None

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=999,
            target_path="/path/to/track.flac",
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_download(decision, result)

        assert result.downloads_attempted == 1
        assert result.downloads_successful == 0
        assert result.downloads_failed == 1
        assert len(result.errors) == 1
        assert "not found in database" in result.errors[0]

    def test_execute_download_dry_run(self, dry_run_orchestrator):
        """Test download execution in dry-run mode."""
        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path="/path/to/track.flac",
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        dry_run_orchestrator._execute_download(decision, result)

        assert result.downloads_attempted == 1
        assert result.downloads_successful == 1

    def test_execute_download_db_error(self, orchestrator, mock_db_service):
        """Test download execution with database error."""
        track = Track(id=1, tidal_id=123, title="Test Track")
        mock_db_service.get_track_by_id.return_value = track

        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("Database error")
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path="/path/to/track.flac",
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_download(decision, result)

        assert result.downloads_attempted == 1
        assert result.downloads_failed == 1
        assert len(result.errors) == 1
        assert "Database error" in result.errors[0]

    def test_execute_download_with_service_success(
        self, mock_db_service, temp_music_root
    ):
        """Test download execution with TidalDownloadService integration."""
        track = Track(id=1, tidal_id=123, title="Test Track")
        mock_db_service.get_track_by_id.return_value = track

        mock_session = MagicMock()
        mock_track_obj = MagicMock()
        mock_session.merge.return_value = mock_track_obj
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        # Mock download service
        mock_download_service = MagicMock()
        mock_download_service.download_track.return_value = (
            temp_music_root / "track.flac"
        )

        orchestrator = DownloadOrchestrator(
            db_service=mock_db_service,
            music_root=temp_music_root,
            download_service=mock_download_service,
        )

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path=str(temp_music_root / "track.flac"),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_download(decision, result)

        assert result.downloads_attempted == 1
        assert result.downloads_successful == 1
        assert result.downloads_failed == 0
        mock_download_service.download_track.assert_called_once()
        assert mock_track_obj.download_status == DownloadStatus.DOWNLOADED

    def test_execute_download_with_service_failure(
        self, mock_db_service, temp_music_root
    ):
        """Test download execution when TidalDownloadService fails."""
        from tidal_cleanup.services.tidal_download_service import TidalDownloadError

        track = Track(id=1, tidal_id=123, title="Test Track")
        mock_db_service.get_track_by_id.return_value = track

        mock_session = MagicMock()
        mock_track_obj = MagicMock()
        mock_session.merge.return_value = mock_track_obj
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        # Mock download service that fails
        mock_download_service = MagicMock()
        mock_download_service.download_track.side_effect = TidalDownloadError(
            "Download failed"
        )

        orchestrator = DownloadOrchestrator(
            db_service=mock_db_service,
            music_root=temp_music_root,
            download_service=mock_download_service,
        )

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path=str(temp_music_root / "track.flac"),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_download(decision, result)

        assert result.downloads_attempted == 1
        assert result.downloads_successful == 0
        assert result.downloads_failed == 1
        assert len(result.errors) == 1
        assert "Download failed" in result.errors[0]
        assert mock_track_obj.download_status == DownloadStatus.ERROR


class TestExecuteCreateSymlink:
    """Test symlink creation."""

    def test_create_symlink_success(self, orchestrator, temp_music_root):
        """Test successful symlink creation."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"

        # Create target file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        decision = DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            source_path=str(source),
            target_path=str(target),
            playlist_track_id=1,
            reason="Create symlink",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_create_symlink(decision, result)

        assert result.symlinks_created == 1
        assert source.is_symlink()

        # Windows may prepend \\?\ prefix for long paths
        target_link = os.readlink(source)
        if target_link.startswith("\\\\?\\"):
            target_link = target_link[4:]
        assert target_link == str(target)

    def test_create_symlink_missing_paths(self, orchestrator):
        """Test symlink creation with missing paths."""
        decision = DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            source_path=None,
            target_path="/path/to/target",
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_create_symlink(decision, result)

        assert result.symlinks_created == 0
        assert len(result.errors) == 1
        assert "Missing paths" in result.errors[0]

    def test_create_symlink_replaces_existing(self, orchestrator, temp_music_root):
        """Test symlink creation replaces existing file/symlink."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"

        # Create existing file at source
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("existing content")

        # Create target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        decision = DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            source_path=str(source),
            target_path=str(target),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_create_symlink(decision, result)

        assert result.symlinks_created == 1
        assert source.is_symlink()
        assert source.read_text() != "existing content"

    def test_create_symlink_dry_run(self, dry_run_orchestrator, temp_music_root):
        """Test symlink creation in dry-run mode."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"

        decision = DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            source_path=str(source),
            target_path=str(target),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        dry_run_orchestrator._execute_create_symlink(decision, result)

        assert result.symlinks_created == 1
        assert not source.exists()

    def test_create_symlink_creates_parent_dirs(self, orchestrator, temp_music_root):
        """Test symlink creation creates parent directories."""
        source = temp_music_root / "Playlists" / "New" / "Subdir" / "track.flac"
        target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"

        # Create target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        decision = DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            source_path=str(source),
            target_path=str(target),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_create_symlink(decision, result)

        assert result.symlinks_created == 1
        assert source.is_symlink()
        assert source.parent.exists()


class TestExecuteUpdateSymlink:
    """Test symlink update."""

    def test_update_symlink_success(self, orchestrator, temp_music_root):
        """Test successful symlink update."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        old_target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"
        new_target = temp_music_root / "Playlists" / "Playlist3" / "track.flac"

        # Create old symlink
        source.parent.mkdir(parents=True, exist_ok=True)
        old_target.parent.mkdir(parents=True, exist_ok=True)
        old_target.touch()
        os.symlink(old_target, source)

        # Create new target
        new_target.parent.mkdir(parents=True, exist_ok=True)
        new_target.touch()

        decision = DecisionResult(
            action=SyncAction.UPDATE_SYMLINK,
            source_path=str(source),
            target_path=str(new_target),
            playlist_track_id=1,
            reason="Update symlink",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_update_symlink(decision, result)

        assert result.symlinks_updated == 1
        assert source.is_symlink()

        # Windows may prepend \\?\ prefix for long paths
        target_link = os.readlink(source)
        if target_link.startswith("\\\\?\\"):
            target_link = target_link[4:]
        assert target_link == str(new_target)

    def test_update_symlink_missing_paths(self, orchestrator):
        """Test symlink update with missing paths."""
        decision = DecisionResult(
            action=SyncAction.UPDATE_SYMLINK,
            source_path=str("/path/to/source"),
            target_path=None,
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_update_symlink(decision, result)

        assert result.symlinks_updated == 0
        assert len(result.errors) == 1
        assert "Missing paths" in result.errors[0]

    def test_update_symlink_dry_run(self, dry_run_orchestrator, temp_music_root):
        """Test symlink update in dry-run mode."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        new_target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"

        decision = DecisionResult(
            action=SyncAction.UPDATE_SYMLINK,
            source_path=str(source),
            target_path=str(new_target),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        dry_run_orchestrator._execute_update_symlink(decision, result)

        assert result.symlinks_updated == 1


class TestExecuteRemoveSymlink:
    """Test symlink removal."""

    def test_remove_symlink_success(self, orchestrator, temp_music_root):
        """Test successful symlink removal."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"

        # Create symlink
        source.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        os.symlink(target, source)

        decision = DecisionResult(
            action=SyncAction.REMOVE_SYMLINK,
            source_path=str(source),
            playlist_track_id=1,
            reason="Remove symlink",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_remove_symlink(decision, result)

        assert result.symlinks_removed == 1
        assert not source.exists()

    def test_remove_symlink_missing_path(self, orchestrator):
        """Test symlink removal with missing path."""
        decision = DecisionResult(
            action=SyncAction.REMOVE_SYMLINK,
            source_path=None,
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_remove_symlink(decision, result)

        assert result.symlinks_removed == 0
        assert len(result.errors) == 1
        assert "Missing source path" in result.errors[0]

    def test_remove_symlink_not_symlink(self, orchestrator, temp_music_root, caplog):
        """Test symlink removal when path is not a symlink."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("regular file")

        decision = DecisionResult(
            action=SyncAction.REMOVE_SYMLINK,
            source_path=str(source),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_remove_symlink(decision, result)

        assert result.symlinks_removed == 0
        assert "not a symlink" in caplog.text
        assert source.exists()  # File not removed

    def test_remove_symlink_dry_run(self, dry_run_orchestrator, temp_music_root):
        """Test symlink removal in dry-run mode."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        target = temp_music_root / "Playlists" / "Playlist2" / "track.flac"

        # Create symlink
        source.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        os.symlink(target, source)

        decision = DecisionResult(
            action=SyncAction.REMOVE_SYMLINK,
            source_path=str(source),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        dry_run_orchestrator._execute_remove_symlink(decision, result)

        assert result.symlinks_removed == 1
        assert source.exists()  # Not actually removed in dry-run


class TestExecuteRemoveFile:
    """Test file removal."""

    def test_remove_file_success(self, orchestrator, temp_music_root):
        """Test successful file removal."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("file content")

        decision = DecisionResult(
            action=SyncAction.REMOVE_FILE,
            source_path=str(source),
            track_id=1,
            reason="Remove file",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_remove_file(decision, result)

        assert result.files_removed == 1
        assert not source.exists()

    def test_remove_file_missing_path(self, orchestrator):
        """Test file removal with missing path."""
        decision = DecisionResult(
            action=SyncAction.REMOVE_FILE,
            source_path=None,
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_remove_file(decision, result)

        assert result.files_removed == 0
        assert len(result.errors) == 1
        assert "Missing source path" in result.errors[0]

    def test_remove_file_not_exists(self, orchestrator, temp_music_root, caplog):
        """Test file removal when file doesn't exist."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"

        decision = DecisionResult(
            action=SyncAction.REMOVE_FILE,
            source_path=str(source),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        orchestrator._execute_remove_file(decision, result)

        assert result.files_removed == 0
        assert "does not exist" in caplog.text

    def test_remove_file_dry_run(self, dry_run_orchestrator, temp_music_root):
        """Test file removal in dry-run mode."""
        source = temp_music_root / "Playlists" / "Playlist1" / "track.flac"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("file content")

        decision = DecisionResult(
            action=SyncAction.REMOVE_FILE,
            source_path=str(source),
            reason="Test",
            priority=5,
        )

        result = ExecutionResult()
        dry_run_orchestrator._execute_remove_file(decision, result)

        assert result.files_removed == 1
        assert source.exists()  # Not actually removed in dry-run


class TestEnsurePlaylistDirectories:
    """Test playlist directory creation."""

    def test_ensure_directories_all_playlists(
        self, orchestrator, mock_db_service, temp_music_root
    ):
        """Test creating directories for all playlists."""
        playlists = [
            Playlist(id=1, tidal_id="p1", name="Playlist 1"),
            Playlist(id=2, tidal_id="p2", name="Playlist 2"),
            Playlist(id=3, tidal_id="p3", name="Playlist 3"),
        ]
        mock_db_service.get_all_playlists.return_value = playlists

        created = orchestrator.ensure_playlist_directories()

        assert created == 3
        assert (temp_music_root / "Playlists" / "Playlist 1").exists()
        assert (temp_music_root / "Playlists" / "Playlist 2").exists()
        assert (temp_music_root / "Playlists" / "Playlist 3").exists()

    def test_ensure_directories_specific_playlists(
        self, orchestrator, mock_db_service, temp_music_root
    ):
        """Test creating directories for specific playlists."""
        playlist1 = Playlist(id=1, tidal_id="p1", name="Playlist 1")
        playlist2 = Playlist(id=2, tidal_id="p2", name="Playlist 2")

        mock_db_service.get_playlist_by_id.side_effect = lambda pid: {
            1: playlist1,
            2: playlist2,
            3: None,
        }.get(pid)

        created = orchestrator.ensure_playlist_directories([1, 2, 3])

        assert created == 2
        assert (temp_music_root / "Playlists" / "Playlist 1").exists()
        assert (temp_music_root / "Playlists" / "Playlist 2").exists()

    def test_ensure_directories_already_exist(
        self, orchestrator, mock_db_service, temp_music_root
    ):
        """Test when directories already exist."""
        playlists = [Playlist(id=1, tidal_id="p1", name="Playlist 1")]
        mock_db_service.get_all_playlists.return_value = playlists

        # Create directory first
        (temp_music_root / "Playlists" / "Playlist 1").mkdir(parents=True)

        created = orchestrator.ensure_playlist_directories()

        assert created == 0

    def test_ensure_directories_dry_run(
        self, dry_run_orchestrator, mock_db_service, temp_music_root
    ):
        """Test directory creation in dry-run mode."""
        playlists = [Playlist(id=1, tidal_id="p1", name="Playlist 1")]
        mock_db_service.get_all_playlists.return_value = playlists

        created = dry_run_orchestrator.ensure_playlist_directories()

        assert created == 1
        assert not (temp_music_root / "Playlists" / "Playlist 1").exists()


class TestDatabaseHelperMethods:
    """Test database helper methods."""

    def test_update_symlink_in_db(self, orchestrator, mock_db_service):
        """Test updating symlink information in database."""
        mock_pt = MagicMock(spec=PlaylistTrack)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_pt
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        orchestrator._update_symlink_in_db(
            playlist_track_id=1,
            symlink_path="/path/to/symlink",
            symlink_valid=True,
        )

        assert mock_pt.symlink_path == "/path/to/symlink"
        assert mock_pt.symlink_valid is True
        mock_session.commit.assert_called_once()

    def test_update_symlink_in_db_not_found(self, orchestrator, mock_db_service):
        """Test updating symlink when PlaylistTrack not found."""
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        # Should not raise exception
        orchestrator._update_symlink_in_db(
            playlist_track_id=999,
            symlink_path="/path/to/symlink",
            symlink_valid=True,
        )

    def test_update_track_file_path(self, orchestrator, mock_db_service):
        """Test updating track file path in database."""
        track = Track(id=1, tidal_id=123, title="Test Track")
        mock_db_service.get_track_by_id.return_value = track

        mock_session = MagicMock()
        mock_track_obj = MagicMock()
        mock_session.merge.return_value = mock_track_obj
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        orchestrator._update_track_file_path(track_id=1, file_path="/path/to/file.flac")

        assert mock_track_obj.file_path == "/path/to/file.flac"
        mock_session.commit.assert_called_once()

    def test_update_track_file_path_to_none(self, orchestrator, mock_db_service):
        """Test updating track file path to None (marks as not downloaded)."""
        track = Track(id=1, tidal_id=123, title="Test Track")
        mock_db_service.get_track_by_id.return_value = track

        mock_session = MagicMock()
        mock_track_obj = MagicMock()
        mock_session.merge.return_value = mock_track_obj
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        orchestrator._update_track_file_path(track_id=1, file_path=None)

        assert mock_track_obj.file_path is None
        assert mock_track_obj.download_status == DownloadStatus.NOT_DOWNLOADED
        mock_session.commit.assert_called_once()

    def test_update_track_file_path_not_found(self, orchestrator, mock_db_service):
        """Test updating track file path when track not found."""
        mock_db_service.get_track_by_id.return_value = None

        # Should not raise exception
        orchestrator._update_track_file_path(
            track_id=999, file_path="/path/to/file.flac"
        )


class TestDownloadOrchestratorEdgeCases:
    """Test edge cases and error paths in DownloadOrchestrator."""

    def test_execute_decisions_with_conflicts(
        self, orchestrator, mock_db_service, caplog
    ):
        """Test execute_decisions handles conflicts correctly."""
        # Mock conflict resolver to return conflicts
        conflict1 = [
            DecisionResult(
                action=SyncAction.DOWNLOAD_TRACK,
                track_id=1,
                target_path="/path1",
                priority=5,
            ),
            DecisionResult(
                action=SyncAction.REMOVE_FILE,
                track_id=1,
                source_path="/path1",
                priority=3,
            ),
        ]

        orchestrator.conflict_resolver.detect_decision_conflicts = MagicMock(
            return_value=[conflict1]
        )
        orchestrator.conflict_resolver.resolve_decision_conflicts = MagicMock(
            return_value=[conflict1[0]]  # Keep higher priority
        )

        decisions = SyncDecisions()
        decisions.add_decision(conflict1[0])
        decisions.add_decision(conflict1[1])

        # Mock track for download
        track = Track(id=1, tidal_id="123", title="Test")
        mock_db_service.get_track_by_id.return_value = track

        exec_result = orchestrator.execute_decisions(decisions)

        # Verify conflict detection was called
        orchestrator.conflict_resolver.detect_decision_conflicts.assert_called_once()
        assert "Detected 1 decision conflicts" in caplog.text
        # Note: logger.info doesn't appear in caplog by default, only warnings+
        assert exec_result is not None

    def test_execute_decision_no_action(self, orchestrator):
        """Test _execute_decision with NO_ACTION does nothing."""
        decision = DecisionResult(action=SyncAction.NO_ACTION, priority=1)
        result = ExecutionResult()

        # Should not raise exception
        orchestrator._execute_decision(decision, result)
        assert result.decisions_executed == 0

    def test_execute_decision_unknown_action(self, orchestrator, caplog):
        """Test _execute_decision with unknown action logs warning."""
        decision = DecisionResult(action="UNKNOWN_ACTION", priority=1)
        result = ExecutionResult()

        orchestrator._execute_decision(decision, result)
        assert "Unhandled action type: UNKNOWN_ACTION" in caplog.text

    def test_execute_download_defensive_track_id_none(
        self, orchestrator, mock_db_service
    ):
        """Test _execute_download defensive check for track_id None."""
        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=None,  # Invalid but passed validation somehow
            target_path="/path/to/track.flac",
            priority=5,
        )
        result = ExecutionResult()

        # Mock validation to pass
        orchestrator._validate_download_decision = MagicMock(return_value=True)

        # Should handle gracefully
        orchestrator._execute_download(decision, result)
        # Should return early without error

    def test_execute_download_track_status_update(self, orchestrator, mock_db_service):
        """Test _execute_download updates track status to DOWNLOADING."""
        track = Track(id=1, tidal_id="123", title="Test", download_status="pending")
        mock_db_service.get_track_by_id.return_value = track

        # Mock session for status update
        mock_session = MagicMock()
        mock_track_obj = MagicMock()
        mock_session.merge.return_value = mock_track_obj
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path="/path/to/track.flac",
            priority=5,
        )
        result = ExecutionResult()

        # No download service - will fail but status should update
        orchestrator.download_service = None
        orchestrator._execute_download(decision, result)

        # Verify status was set to DOWNLOADING
        assert mock_track_obj.download_status == DownloadStatus.DOWNLOADING
        mock_session.commit.assert_called()

    def test_handle_no_download_service(self, orchestrator):
        """Test _handle_no_download_service marks as successful."""
        result = ExecutionResult()

        orchestrator._handle_no_download_service(result)

        # Without download service, it just marks as successful
        assert result.downloads_successful == 1
        assert result.downloads_failed == 0

    def test_perform_download_defensive_target_path_none(
        self, orchestrator, mock_db_service
    ):
        """Test _perform_download defensive check for target_path None."""
        track = Track(id=1, tidal_id="123", title="Test")
        mock_db_service.get_track_by_id.return_value = track

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path=None,  # Invalid but passed validation somehow
            priority=5,
        )
        result = ExecutionResult()

        # The exception is caught and logged in _execute_download, not raised
        # Test that it's caught properly by calling through _execute_download
        orchestrator._execute_download(decision, result)

        # Should have resulted in a failed download
        assert result.downloads_failed == 1
        assert len(result.errors) > 0

    def test_perform_download_defensive_download_service_none(
        self, orchestrator, mock_db_service
    ):
        """Test _perform_download defensive check for download_service None."""
        track = Track(id=1, tidal_id="123", title="Test")
        mock_db_service.get_track_by_id.return_value = track

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path="/path/to/track.flac",
            priority=5,
        )
        result = ExecutionResult()

        orchestrator.download_service = None

        # When download_service is None, it calls _handle_no_download_service
        # which marks download as successful (not failed)
        orchestrator._execute_download(decision, result)

        # Should mark as successful even without download service
        assert result.downloads_successful == 1
        assert result.downloads_failed == 0

    def test_get_tidal_track_id_no_tidal_id(self, orchestrator):
        """Test _get_tidal_track_id raises error when track has no tidal_id."""
        track = Track(id=1, tidal_id=None, title="Test")

        with pytest.raises(ValueError, match="Track 1 has no tidal_id"):
            orchestrator._get_tidal_track_id(track)

    @pytest.mark.skipif(
        sys.platform.startswith("win"), reason="Unix-specific permission test"
    )
    def test_execute_create_symlink_exception_handling(
        self, orchestrator, tmp_path, caplog
    ):
        """Test _execute_create_symlink handles exceptions with permissions."""
        # Use a path that will definitely cause an error (e.g., /root)
        source = Path("/root/playlist/track.flac")
        target = tmp_path / "music" / "track.flac"

        decision = DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            source_path=str(source),
            target_path=str(target),
            priority=3,
        )
        result = ExecutionResult()

        orchestrator._execute_create_symlink(decision, result)

        # Should have error due to permission denied
        assert len(result.errors) > 0
        assert "Failed to create symlink" in result.errors[0]

    @pytest.mark.skipif(
        sys.platform.startswith("win"), reason="Unix-specific permission test"
    )
    def test_execute_update_symlink_exception_handling(
        self, orchestrator, tmp_path, caplog
    ):
        """Test _execute_update_symlink handles exceptions with permissions."""
        # Use a path that will definitely cause an error (e.g., /root)
        source = Path("/root/playlist/track.flac")
        target = tmp_path / "music" / "track.flac"

        decision = DecisionResult(
            action=SyncAction.UPDATE_SYMLINK,
            source_path=str(source),
            target_path=str(target),
            priority=3,
        )
        result = ExecutionResult()

        orchestrator._execute_update_symlink(decision, result)

        # Should handle exception due to permission denied
        assert len(result.errors) > 0
        assert "Failed to update symlink" in result.errors[0]

    def test_execute_remove_symlink_exception_handling(
        self, orchestrator, tmp_path, caplog
    ):
        """Test _execute_remove_symlink handles exceptions."""
        # Create a directory instead of symlink
        source = tmp_path / "playlist" / "track_dir"
        source.mkdir(parents=True, exist_ok=True)

        decision = DecisionResult(
            action=SyncAction.REMOVE_SYMLINK,
            source_path=str(source),
            priority=3,
        )
        result = ExecutionResult()

        orchestrator._execute_remove_symlink(decision, result)

        # Should log warning that it's not a symlink
        assert "Path is not a symlink" in caplog.text

    def test_execute_remove_file_exception_handling(self, orchestrator, tmp_path):
        """Test _execute_remove_file handles exceptions."""
        # Create a directory instead of file
        source = tmp_path / "track_dir"
        source.mkdir()

        decision = DecisionResult(
            action=SyncAction.REMOVE_FILE,
            source_path=str(source),
            track_id=1,
            priority=3,
        )
        result = ExecutionResult()

        orchestrator._execute_remove_file(decision, result)

        # Should have error (can't unlink directory with unlink())
        assert len(result.errors) > 0
        assert "Failed to remove file" in result.errors[0]

    def test_ensure_playlist_directories_with_none_playlist(
        self, orchestrator, mock_db_service
    ):
        """Test ensure_playlist_directories handles None in playlist list."""
        # Return one valid and one None - need to handle list comprehension call
        playlist = Playlist(id=1, tidal_id="pl1", name="Test Playlist")

        def side_effect_fn(pid):
            if pid == 1:
                return playlist
            return None

        mock_db_service.get_playlist_by_id.side_effect = side_effect_fn

        created = orchestrator.ensure_playlist_directories(playlist_ids=[1, 999])

        # Should only create for valid playlist
        assert created == 1

    def test_validate_download_decision_missing_target_path(self, orchestrator):
        """Test _validate_download_decision with empty target_path."""
        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path="",  # Empty string
            priority=5,
        )
        result = ExecutionResult()

        is_valid = orchestrator._validate_download_decision(decision, result)

        assert is_valid is False
        assert result.downloads_failed == 1
        assert "target_path is None" in result.errors[0]

    def test_update_track_status_db_session(self, orchestrator, mock_db_service):
        """Test _update_track_status correctly updates database."""
        track = Track(id=1, tidal_id="123", title="Test")

        mock_session = MagicMock()
        mock_track_obj = MagicMock()
        mock_session.merge.return_value = mock_track_obj
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session

        orchestrator._update_track_status(track, DownloadStatus.DOWNLOADING)

        assert mock_track_obj.download_status == DownloadStatus.DOWNLOADING
        mock_session.commit.assert_called_once()

    def test_execute_decisions_exception_in_decision_execution(
        self, orchestrator, mock_db_service, caplog
    ):
        """Test execute_decisions continues after exception in single decision."""
        decision1 = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path="/path1",
            priority=5,
        )
        decision2 = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=2,
            target_path="/path2",
            priority=4,
        )

        decisions = SyncDecisions()
        decisions.add_decision(decision1)
        decisions.add_decision(decision2)

        # First decision will fail
        mock_db_service.get_track_by_id.side_effect = [
            Exception("Database error"),
            Track(id=2, tidal_id="456", title="Track 2"),
        ]

        result = orchestrator.execute_decisions(decisions)

        # Should continue to second decision despite first failing
        assert len(result.errors) > 0
        assert "Failed to download track" in result.errors[0]
        assert "Database error" in result.errors[0]

    def test_perform_download_success_with_valid_service(
        self, orchestrator, mock_db_service, tmp_path
    ):
        """Test _perform_download successfully calls download service."""
        track = Track(id=1, tidal_id="123456", title="Test Track")
        target_path = tmp_path / "track.flac"

        decision = DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=1,
            target_path=str(target_path),
            priority=5,
        )
        result = ExecutionResult()

        # Setup download service mock
        mock_download_service = MagicMock()
        orchestrator.download_service = mock_download_service

        orchestrator._perform_download(track, decision, result)

        # Verify download was called
        mock_download_service.download_track.assert_called_once()
        call_args = mock_download_service.download_track.call_args
        assert call_args[1]["track_id"] == 123456
        assert call_args[1]["target_path"] == target_path
