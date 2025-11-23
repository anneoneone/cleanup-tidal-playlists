"""Tests for SyncOrchestrator."""

from unittest.mock import Mock, patch

import pytest

from tidal_cleanup.config import Config
from tidal_cleanup.database import DatabaseService, SyncOrchestrator, SyncResult
from tidal_cleanup.database.deduplication_logic import (
    DeduplicationResult,
    PrimaryFileDecision,
)
from tidal_cleanup.database.download_orchestrator import ExecutionResult
from tidal_cleanup.database.filesystem_scanner import ScanStatistics
from tidal_cleanup.database.sync_decision_engine import (
    DecisionResult,
    SyncAction,
    SyncDecisions,
)
from tidal_cleanup.database.tidal_state_fetcher import FetchStatistics


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = DatabaseService(str(db_path))
    db.init_db()
    return db


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock config."""
    config = Mock(spec=Config)
    config.m4a_directory = str(tmp_path / "music")
    return config


@pytest.fixture
def mock_download_service():
    """Create a mock download service."""
    service = Mock()
    return service


@pytest.fixture
def sync_orchestrator(mock_config, temp_db, mock_download_service):
    """Create SyncOrchestrator instance."""
    return SyncOrchestrator(
        config=mock_config,
        db_service=temp_db,
        download_service=mock_download_service,
        dry_run=False,
    )


class TestSyncResult:
    """Test SyncResult dataclass."""

    def test_init(self):
        """Test SyncResult initialization."""
        result = SyncResult()

        assert result.tidal_fetch is None
        assert result.filesystem_scan is None
        assert result.deduplication is None
        assert result.decisions is None
        assert result.execution is None
        assert result.errors == []

    def test_add_error(self):
        """Test adding errors."""
        result = SyncResult()

        result.add_error("Error 1")
        result.add_error("Error 2")

        assert len(result.errors) == 2
        assert result.errors[0] == "Error 1"
        assert result.errors[1] == "Error 2"

    def test_get_summary_empty(self):
        """Test get_summary with empty result."""
        result = SyncResult()

        summary = result.get_summary()

        assert summary["success"] is True
        assert summary["errors"] == 0
        assert "tidal" not in summary
        assert "filesystem" not in summary

    def test_get_summary_with_errors(self):
        """Test get_summary with errors."""
        result = SyncResult()
        result.add_error("Test error")

        summary = result.get_summary()

        assert summary["success"] is False
        assert summary["errors"] == 1

    def test_get_summary_with_tidal_fetch(self):
        """Test get_summary with tidal fetch stats."""
        result = SyncResult()
        result.tidal_fetch = FetchStatistics(
            playlists_fetched=5, tracks_created=10, tracks_updated=3
        )

        summary = result.get_summary()

        assert "tidal" in summary
        assert summary["tidal"]["playlists_fetched"] == 5
        assert summary["tidal"]["tracks_created"] == 10
        assert summary["tidal"]["tracks_updated"] == 3

    def test_get_summary_with_filesystem_scan(self):
        """Test get_summary with filesystem scan stats."""
        result = SyncResult()
        result.filesystem_scan = ScanStatistics(
            playlists_scanned=3, files_found=50, symlinks_found=5
        )

        summary = result.get_summary()

        assert "filesystem" in summary
        assert summary["filesystem"]["playlists_scanned"] == 3
        assert summary["filesystem"]["files_found"] == 50

    def test_get_summary_with_deduplication(self):
        """Test get_summary with deduplication result."""
        result = SyncResult()
        dedup_result = DeduplicationResult()
        dedup_result.decisions.append(
            PrimaryFileDecision(
                track_id=1,
                primary_playlist_id=1,
                primary_playlist_name="Playlist 1",
                symlink_playlist_ids=[2, 3],
                reason="Test decision",
            )
        )

        result.deduplication = dedup_result

        summary = result.get_summary()

        assert "deduplication" in summary
        assert summary["deduplication"]["tracks_analyzed"] == 1
        assert summary["deduplication"]["symlinks_needed"] == 2

    def test_get_summary_with_decisions(self):
        """Test get_summary with sync decisions."""
        result = SyncResult()
        decisions = SyncDecisions()

        # Add download decision
        download_decision = DecisionResult(
            playlist_id=1,
            track_id=1,
            action=SyncAction.DOWNLOAD_TRACK,
            reason="Track not found",
        )
        decisions.add_decision(download_decision)

        # Add symlink decision
        symlink_decision = DecisionResult(
            playlist_id=2,
            track_id=1,
            action=SyncAction.CREATE_SYMLINK,
            reason="Duplicate track",
        )
        decisions.add_decision(symlink_decision)

        result.decisions = decisions

        summary = result.get_summary()

        assert "decisions" in summary
        assert summary["decisions"]["total"] == 2
        assert summary["decisions"]["downloads"] == 1
        assert summary["decisions"]["symlinks"] == 1

    def test_get_summary_with_execution(self):
        """Test get_summary with execution result."""
        result = SyncResult()
        execution = ExecutionResult()
        execution.tracks_downloaded = 5
        execution.symlinks_created = 3

        result.execution = execution

        summary = result.get_summary()

        assert "execution" in summary


class TestSyncOrchestratorInit:
    """Test SyncOrchestrator initialization."""

    def test_init_with_download_service(
        self, mock_config, temp_db, mock_download_service
    ):
        """Test initialization with download service."""
        orchestrator = SyncOrchestrator(
            config=mock_config,
            db_service=temp_db,
            download_service=mock_download_service,
            dry_run=False,
        )

        assert orchestrator.config == mock_config
        assert orchestrator.db_service == temp_db
        assert orchestrator.download_service == mock_download_service
        assert orchestrator.dry_run is False
        assert orchestrator.tidal_fetcher is not None
        assert orchestrator.filesystem_scanner is not None
        assert orchestrator.dedup_logic is not None
        assert orchestrator.decision_engine is not None
        assert orchestrator.download_orchestrator is not None

    def test_init_without_download_service(self, mock_config, temp_db):
        """Test initialization without download service."""
        orchestrator = SyncOrchestrator(
            config=mock_config, db_service=temp_db, dry_run=True
        )

        assert orchestrator.download_service is None
        assert orchestrator.dry_run is True

    def test_init_creates_all_components(self, sync_orchestrator):
        """Test that all components are created."""
        assert sync_orchestrator.tidal_fetcher is not None
        assert sync_orchestrator.filesystem_scanner is not None
        assert sync_orchestrator.dedup_logic is not None
        assert sync_orchestrator.decision_engine is not None
        assert sync_orchestrator.download_orchestrator is not None


class TestSyncAll:
    """Test sync_all method."""

    def test_sync_all_full_sync(self, sync_orchestrator):
        """Test full sync with all steps enabled."""
        # Mock all components
        sync_orchestrator.tidal_fetcher.fetch_all_playlists = Mock(return_value=[])
        sync_orchestrator.filesystem_scanner.scan_all_playlists = Mock(return_value={})
        sync_orchestrator.filesystem_scanner._stats = ScanStatistics()
        sync_orchestrator.dedup_logic.analyze_all_tracks = Mock(
            return_value=DeduplicationResult()
        )
        sync_orchestrator.decision_engine.analyze_all_playlists = Mock(
            return_value=SyncDecisions()
        )
        sync_orchestrator.download_orchestrator.execute_decisions = Mock(
            return_value=ExecutionResult()
        )

        result = sync_orchestrator.sync_all(
            fetch_tidal=True, scan_filesystem=True, analyze_deduplication=True
        )

        assert result is not None
        assert result.tidal_fetch is not None
        assert result.filesystem_scan is not None
        assert result.deduplication is not None
        assert result.decisions is not None
        assert result.execution is not None

    def test_sync_all_fetch_tidal_only(self, sync_orchestrator):
        """Test sync with only Tidal fetch enabled."""
        sync_orchestrator.tidal_fetcher.fetch_all_playlists = Mock(return_value=[])
        sync_orchestrator.decision_engine.analyze_all_playlists = Mock(
            return_value=SyncDecisions()
        )
        sync_orchestrator.download_orchestrator.execute_decisions = Mock(
            return_value=ExecutionResult()
        )

        result = sync_orchestrator.sync_all(
            fetch_tidal=True, scan_filesystem=False, analyze_deduplication=False
        )

        assert result.tidal_fetch is not None
        assert result.filesystem_scan is None
        assert result.deduplication is None

    def test_sync_all_scan_filesystem_only(self, sync_orchestrator):
        """Test sync with only filesystem scan enabled."""
        sync_orchestrator.filesystem_scanner.scan_all_playlists = Mock(return_value={})
        sync_orchestrator.filesystem_scanner._stats = ScanStatistics()
        sync_orchestrator.decision_engine.analyze_all_playlists = Mock(
            return_value=SyncDecisions()
        )
        sync_orchestrator.download_orchestrator.execute_decisions = Mock(
            return_value=ExecutionResult()
        )

        result = sync_orchestrator.sync_all(
            fetch_tidal=False, scan_filesystem=True, analyze_deduplication=False
        )

        assert result.tidal_fetch is None
        assert result.filesystem_scan is not None
        assert result.deduplication is None

    def test_sync_all_analyze_deduplication_only(self, sync_orchestrator):
        """Test sync with only deduplication analysis enabled."""
        sync_orchestrator.dedup_logic.analyze_all_tracks = Mock(
            return_value=DeduplicationResult()
        )
        sync_orchestrator.decision_engine.analyze_all_playlists = Mock(
            return_value=SyncDecisions()
        )
        sync_orchestrator.download_orchestrator.execute_decisions = Mock(
            return_value=ExecutionResult()
        )

        result = sync_orchestrator.sync_all(
            fetch_tidal=False, scan_filesystem=False, analyze_deduplication=True
        )

        assert result.tidal_fetch is None
        assert result.filesystem_scan is None
        assert result.deduplication is not None

    def test_sync_all_with_errors_in_tidal_fetch(self, sync_orchestrator):
        """Test sync_all handles errors in tidal fetch."""
        # Create stats with errors
        stats = FetchStatistics()
        stats.errors.append("Test error")

        with (
            patch.object(sync_orchestrator, "_fetch_tidal_state", return_value=stats),
            patch.object(
                sync_orchestrator, "_scan_filesystem", return_value=ScanStatistics()
            ),
            patch.object(
                sync_orchestrator,
                "_analyze_deduplication",
                return_value=DeduplicationResult(),
            ),
            patch.object(
                sync_orchestrator,
                "_generate_decisions",
                return_value=SyncDecisions(),
            ),
            patch.object(
                sync_orchestrator,
                "_execute_decisions",
                return_value=ExecutionResult(),
            ),
        ):
            result = sync_orchestrator.sync_all(
                fetch_tidal=True,
                scan_filesystem=False,
                analyze_deduplication=False,
            )

            assert len(result.errors) == 1
            assert "Tidal fetch error" in result.errors[0]

    def test_sync_all_with_errors_in_filesystem_scan(self, sync_orchestrator):
        """Test sync_all handles errors in filesystem scan."""
        # Create stats with errors
        stats = ScanStatistics()
        stats.errors.append("Scan error")

        with (
            patch.object(
                sync_orchestrator, "_fetch_tidal_state", return_value=FetchStatistics()
            ),
            patch.object(sync_orchestrator, "_scan_filesystem", return_value=stats),
            patch.object(
                sync_orchestrator,
                "_analyze_deduplication",
                return_value=DeduplicationResult(),
            ),
            patch.object(
                sync_orchestrator,
                "_generate_decisions",
                return_value=SyncDecisions(),
            ),
            patch.object(
                sync_orchestrator,
                "_execute_decisions",
                return_value=ExecutionResult(),
            ),
        ):
            result = sync_orchestrator.sync_all(
                fetch_tidal=False,
                scan_filesystem=True,
                analyze_deduplication=False,
            )

            assert len(result.errors) == 1
            assert "Filesystem scan error" in result.errors[0]

    def test_sync_all_with_errors_in_execution(self, sync_orchestrator):
        """Test sync_all handles errors in execution."""
        # Create execution result with errors
        execution = ExecutionResult()
        execution.errors.append("Execution error")

        with (
            patch.object(
                sync_orchestrator, "_fetch_tidal_state", return_value=FetchStatistics()
            ),
            patch.object(
                sync_orchestrator, "_scan_filesystem", return_value=ScanStatistics()
            ),
            patch.object(
                sync_orchestrator,
                "_analyze_deduplication",
                return_value=DeduplicationResult(),
            ),
            patch.object(
                sync_orchestrator,
                "_generate_decisions",
                return_value=SyncDecisions(),
            ),
            patch.object(
                sync_orchestrator,
                "_execute_decisions",
                return_value=execution,
            ),
        ):
            result = sync_orchestrator.sync_all()

            assert len(result.errors) == 1
            assert "Execution error" in result.errors[0]

    def test_sync_all_with_exception(self, sync_orchestrator):
        """Test sync_all handles exceptions."""
        sync_orchestrator.tidal_fetcher.fetch_all_playlists = Mock(
            side_effect=Exception("Test exception")
        )

        result = sync_orchestrator.sync_all(fetch_tidal=True)

        assert len(result.errors) > 0
        assert "Sync operation failed" in result.errors[0]

    def test_sync_all_decision_generation_failure(self, sync_orchestrator):
        """Test sync_all when decision generation returns None."""
        with (
            patch.object(
                sync_orchestrator, "_fetch_tidal_state", return_value=FetchStatistics()
            ),
            patch.object(
                sync_orchestrator, "_scan_filesystem", return_value=ScanStatistics()
            ),
            patch.object(
                sync_orchestrator,
                "_analyze_deduplication",
                return_value=DeduplicationResult(),
            ),
            patch.object(sync_orchestrator, "_generate_decisions", return_value=None),
        ):
            result = sync_orchestrator.sync_all()

            assert len(result.errors) == 1
            assert "Failed to generate sync decisions" in result.errors[0]
            assert result.execution is None


class TestSyncPlaylist:
    """Test sync_playlist method."""

    def test_sync_playlist_success(self, sync_orchestrator, temp_db):
        """Test syncing a specific playlist."""
        # Create playlist in database
        temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )

        # Mock all operations
        with (
            patch.object(
                sync_orchestrator, "_fetch_tidal_state", return_value=FetchStatistics()
            ),
            patch.object(
                sync_orchestrator, "_scan_filesystem", return_value=ScanStatistics()
            ),
            patch.object(
                sync_orchestrator,
                "_analyze_deduplication",
                return_value=DeduplicationResult(),
            ),
            patch.object(
                sync_orchestrator,
                "_generate_decisions",
                return_value=SyncDecisions(),
            ),
            patch.object(
                sync_orchestrator,
                "_execute_decisions",
                return_value=ExecutionResult(),
            ),
        ):
            result = sync_orchestrator.sync_playlist("Test Playlist")

            assert result is not None
            assert result.tidal_fetch is not None
            assert result.filesystem_scan is not None
            assert result.deduplication is not None
            assert result.decisions is not None
            assert result.execution is not None

    def test_sync_playlist_not_found(self, sync_orchestrator, temp_db):
        """Test syncing a non-existent playlist."""
        result = sync_orchestrator.sync_playlist("Nonexistent Playlist")

        assert len(result.errors) == 1
        assert "not found in database" in result.errors[0]
        assert result.tidal_fetch is None

    def test_sync_playlist_with_exception(self, sync_orchestrator, temp_db):
        """Test sync_playlist handles exceptions."""
        # Create playlist
        temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )

        # Mock to raise exception
        with patch.object(
            sync_orchestrator,
            "_fetch_tidal_state",
            side_effect=Exception("Test exception"),
        ):
            result = sync_orchestrator.sync_playlist("Test Playlist")

            assert len(result.errors) == 1
            assert "Playlist sync failed" in result.errors[0]


class TestHelperMethods:
    """Test helper methods."""

    def test_fetch_tidal_state_all_playlists(self, sync_orchestrator):
        """Test fetching all playlists from Tidal."""
        mock_playlists = [Mock(), Mock(), Mock()]
        sync_orchestrator.tidal_fetcher.fetch_all_playlists = Mock(
            return_value=mock_playlists
        )

        stats = sync_orchestrator._fetch_tidal_state()

        assert stats.playlists_fetched == 3

    def test_fetch_tidal_state_specific_playlists(self, sync_orchestrator):
        """Test fetching specific playlists from Tidal."""
        stats = sync_orchestrator._fetch_tidal_state(playlist_ids=[1, 2])

        assert stats.playlists_fetched == 2

    def test_scan_filesystem(self, sync_orchestrator):
        """Test scanning filesystem."""
        sync_orchestrator.filesystem_scanner.scan_all_playlists = Mock(return_value={})
        sync_orchestrator.filesystem_scanner._stats = ScanStatistics(
            playlists_scanned=5, files_found=100
        )

        stats = sync_orchestrator._scan_filesystem()

        assert stats.playlists_scanned == 5
        assert stats.files_found == 100

    def test_scan_filesystem_with_filter(self, sync_orchestrator):
        """Test scanning filesystem with playlist filter."""
        sync_orchestrator.filesystem_scanner.scan_all_playlists = Mock(return_value={})
        sync_orchestrator.filesystem_scanner._stats = ScanStatistics()

        stats = sync_orchestrator._scan_filesystem(
            playlist_filter=["Playlist 1", "Playlist 2"]
        )

        assert stats is not None

    def test_analyze_deduplication_all_tracks(self, sync_orchestrator):
        """Test analyzing all tracks for deduplication."""
        mock_result = DeduplicationResult()
        sync_orchestrator.dedup_logic.analyze_all_tracks = Mock(
            return_value=mock_result
        )

        result = sync_orchestrator._analyze_deduplication()

        assert result == mock_result
        sync_orchestrator.dedup_logic.analyze_all_tracks.assert_called_once()

    def test_analyze_deduplication_specific_playlists(self, sync_orchestrator, temp_db):
        """Test analyzing specific playlists for deduplication."""
        # Create playlist and track
        playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )
        track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
                "album": "Album 1",
            }
        )
        temp_db.add_track_to_playlist(playlist.id, track.id, position=0)

        # Mock deduplication logic
        mock_decision = PrimaryFileDecision(
            track_id=track.id,
            primary_playlist_id=playlist.id,
            primary_playlist_name="Test Playlist",
            symlink_playlist_ids=[],
            reason="Test",
        )
        sync_orchestrator.dedup_logic.analyze_track_distribution = Mock(
            return_value=mock_decision
        )

        result = sync_orchestrator._analyze_deduplication(playlist_ids=[playlist.id])

        assert len(result.decisions) == 1
        assert result.decisions[0] == mock_decision

    def test_analyze_deduplication_no_decision_returned(
        self, sync_orchestrator, temp_db
    ):
        """Test analyzing when no deduplication decision is returned."""
        # Create playlist and track
        playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )
        track = temp_db.create_track(
            {
                "tidal_id": "tr123",
                "title": "Track 1",
                "artist": "Artist 1",
                "album": "Album 1",
            }
        )
        temp_db.add_track_to_playlist(playlist.id, track.id, position=0)

        # Mock to return None
        sync_orchestrator.dedup_logic.analyze_track_distribution = Mock(
            return_value=None
        )

        result = sync_orchestrator._analyze_deduplication(playlist_ids=[playlist.id])

        assert len(result.decisions) == 0

    def test_generate_decisions_all_playlists(self, sync_orchestrator):
        """Test generating decisions for all playlists."""
        mock_decisions = SyncDecisions()
        sync_orchestrator.decision_engine.analyze_all_playlists = Mock(
            return_value=mock_decisions
        )

        decisions = sync_orchestrator._generate_decisions()

        assert decisions == mock_decisions
        sync_orchestrator.decision_engine.analyze_all_playlists.assert_called_once()

    def test_generate_decisions_specific_playlists(self, sync_orchestrator, temp_db):
        """Test generating decisions for specific playlists."""
        # Create playlist
        db_playlist = temp_db.create_playlist(
            {
                "tidal_id": "pl123",
                "name": "Test Playlist",
                "description": "Test",
            }
        )

        # Mock decision engine
        mock_playlist_decisions = SyncDecisions()
        mock_decision = DecisionResult(
            playlist_id=db_playlist.id,
            track_id=1,
            action=SyncAction.DOWNLOAD_TRACK,
            reason="Test",
        )
        mock_playlist_decisions.add_decision(mock_decision)

        sync_orchestrator.decision_engine.analyze_playlist_sync = Mock(
            return_value=mock_playlist_decisions
        )

        decisions = sync_orchestrator._generate_decisions(playlist_ids=[db_playlist.id])

        assert len(decisions.decisions) == 1

    def test_execute_decisions(self, sync_orchestrator):
        """Test executing sync decisions."""
        decisions = SyncDecisions()
        mock_result = ExecutionResult()

        sync_orchestrator.download_orchestrator.execute_decisions = Mock(
            return_value=mock_result
        )

        result = sync_orchestrator._execute_decisions(decisions)

        assert result == mock_result
        execute_mock = sync_orchestrator.download_orchestrator.execute_decisions
        execute_mock.assert_called_once_with(decisions)

    def test_collect_errors(self, sync_orchestrator):
        """Test collecting errors from a step."""
        result = SyncResult()
        errors = ["Error 1", "Error 2"]

        sync_orchestrator._collect_errors(result, errors, "Test prefix")

        assert len(result.errors) == 2
        assert "Test prefix: Error 1" in result.errors[0]
        assert "Test prefix: Error 2" in result.errors[1]

    def test_collect_errors_empty_list(self, sync_orchestrator):
        """Test collecting errors with empty list."""
        result = SyncResult()

        sync_orchestrator._collect_errors(result, [], "Test prefix")

        assert len(result.errors) == 0

    def test_log_sync_summary(self, sync_orchestrator):
        """Test logging sync summary."""
        result = SyncResult()
        result.tidal_fetch = FetchStatistics(playlists_fetched=5)

        # Should not raise exception
        sync_orchestrator._log_sync_summary(result)

    def test_handle_sync_error(self, sync_orchestrator):
        """Test handling sync error."""
        result = SyncResult()
        error = Exception("Test exception")

        sync_orchestrator._handle_sync_error(result, error)

        assert len(result.errors) == 1
        assert "Sync operation failed" in result.errors[0]


class TestEnsureDirectories:
    """Test ensure_directories method."""

    def test_ensure_directories(self, sync_orchestrator):
        """Test ensuring playlist directories exist."""
        with patch.object(
            sync_orchestrator.download_orchestrator,
            "ensure_playlist_directories",
            return_value=3,
        ) as mock_ensure:
            count = sync_orchestrator.ensure_directories()

            assert count == 3
            mock_ensure.assert_called_once()


class TestStepMethods:
    """Test individual step execution methods."""

    def test_execute_tidal_fetch_step(self, sync_orchestrator):
        """Test executing tidal fetch step."""
        result = SyncResult()
        stats = FetchStatistics(playlists_fetched=5)

        with patch.object(sync_orchestrator, "_fetch_tidal_state", return_value=stats):
            sync_orchestrator._execute_tidal_fetch_step(result)

            assert result.tidal_fetch == stats

    def test_execute_filesystem_scan_step(self, sync_orchestrator):
        """Test executing filesystem scan step."""
        result = SyncResult()
        stats = ScanStatistics(playlists_scanned=3)

        with patch.object(sync_orchestrator, "_scan_filesystem", return_value=stats):
            sync_orchestrator._execute_filesystem_scan_step(result)

            assert result.filesystem_scan == stats

    def test_execute_deduplication_step(self, sync_orchestrator):
        """Test executing deduplication step."""
        result = SyncResult()
        dedup_result = DeduplicationResult()

        with patch.object(
            sync_orchestrator, "_analyze_deduplication", return_value=dedup_result
        ):
            sync_orchestrator._execute_deduplication_step(result)

            assert result.deduplication == dedup_result

    def test_execute_decision_generation_step_success(self, sync_orchestrator):
        """Test executing decision generation step successfully."""
        result = SyncResult()
        decisions = SyncDecisions()

        with patch.object(
            sync_orchestrator, "_generate_decisions", return_value=decisions
        ):
            success = sync_orchestrator._execute_decision_generation_step(result)

            assert success is True
            assert result.decisions == decisions

    def test_execute_decision_generation_step_failure(self, sync_orchestrator):
        """Test executing decision generation step with failure."""
        result = SyncResult()

        with patch.object(sync_orchestrator, "_generate_decisions", return_value=None):
            success = sync_orchestrator._execute_decision_generation_step(result)

            assert success is False
            assert len(result.errors) == 1
            assert "Failed to generate sync decisions" in result.errors[0]

    def test_execute_decision_execution_step(self, sync_orchestrator):
        """Test executing decision execution step."""
        result = SyncResult()
        decisions = SyncDecisions()
        result.decisions = decisions
        execution = ExecutionResult()

        with patch.object(
            sync_orchestrator, "_execute_decisions", return_value=execution
        ):
            sync_orchestrator._execute_decision_execution_step(result)

            assert result.execution == execution

    def test_execute_decision_execution_step_no_decisions(self, sync_orchestrator):
        """Test executing decision execution step when decisions is None."""
        result = SyncResult()
        result.decisions = None

        sync_orchestrator._execute_decision_execution_step(result)

        # Should return without error
        assert result.execution is None
