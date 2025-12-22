"""Unified sync orchestrator for coordinating all sync components.

This module provides the high-level SyncOrchestrator that coordinates:
- TidalStateFetcher: Fetches current state from Tidal
- FilesystemScanner: Scans local filesystem state
- SyncDecisionEngine: Determines what actions to take
- DeduplicationLogic: Determines primary file locations
- DownloadOrchestrator: Executes sync decisions
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from pathlib import Path
from typing import Any, List

from ...config import Config
from ...database.service import DatabaseService
from ..filesystem.scanner import FilesystemScanner, ScanStatistics
from ..tidal.download_service import TidalDownloadService
from ..tidal.state_fetcher import FetchStatistics, TidalStateFetcher
from .decision_engine import SyncDecisionEngine, SyncDecisions
from .deduplication import DeduplicationLogic, DeduplicationResult
from .download_orchestrator import DownloadOrchestrator, ExecutionResult

logger = logging.getLogger(__name__)


class SyncStage(str, Enum):
    """Ordered sync stages used for staging runs."""

    FETCH = "fetch"
    SCAN = "scan"
    DEDUP = "dedup"
    DECISIONS = "decisions"
    EXECUTION = "execution"

    @classmethod
    def ordered(cls) -> List["SyncStage"]:
        """Return stages in execution order."""
        return [cls.FETCH, cls.SCAN, cls.DEDUP, cls.DECISIONS, cls.EXECUTION]


@dataclass
class SyncResult:
    """Result of a complete sync operation."""

    tidal_fetch: FetchStatistics | None = None
    filesystem_scan: ScanStatistics | None = None
    deduplication: DeduplicationResult | None = None
    decisions: SyncDecisions | None = None
    execution: ExecutionResult | None = None
    errors: List[str] = dataclass_field(default_factory=list)
    stop_requested: SyncStage | None = None
    stopped_after: SyncStage | None = None

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        logger.error(error)

    def get_summary(self) -> dict[str, Any]:
        """Get summary of sync operation."""
        summary: dict[str, Any] = {
            "success": len(self.errors) == 0,
            "errors": len(self.errors),
        }

        if self.stop_requested or self.stopped_after:
            summary["stage"] = {
                "requested": (
                    self.stop_requested.value if self.stop_requested else None
                ),
                "completed": (self.stopped_after.value if self.stopped_after else None),
            }

        if self.tidal_fetch:
            summary["tidal"] = {
                "playlists_fetched": self.tidal_fetch.playlists_fetched,
                "tracks_created": self.tidal_fetch.tracks_created,
                "tracks_updated": self.tidal_fetch.tracks_updated,
            }

        if self.filesystem_scan:
            summary["filesystem"] = {
                "playlists_scanned": self.filesystem_scan.playlists_scanned,
                "files_found": self.filesystem_scan.files_found,
            }

        if self.deduplication:
            summary["deduplication"] = {
                "tracks_analyzed": len(self.deduplication.distributions),
                "tracks_in_multiple_playlists": (
                    self.deduplication.tracks_in_multiple_playlists
                ),
            }

        if self.decisions:
            downloads = [
                d for d in self.decisions.decisions if d.action.name == "DOWNLOAD_TRACK"
            ]
            summary["decisions"] = {
                "total": len(self.decisions.decisions),
                "downloads": len(downloads),
            }

        if self.execution:
            summary["execution"] = self.execution.get_summary()

        return summary


class SyncOrchestrator:
    """Orchestrates complete sync operation between Tidal and filesystem.

    Coordinates all sync components to provide a unified sync workflow:
    1. Fetch current state from Tidal API
    2. Scan local filesystem state
    3. Analyze deduplication needs
    4. Generate sync decisions
    5. Execute sync decisions
    """

    def __init__(
        self,
        config: Config,
        db_service: DatabaseService,
        tidal_download_service: TidalDownloadService | None = None,
        tidal_session: Any | None = None,
        dry_run: bool = False,
    ):
        """Initialize sync orchestrator.

        Args:
            config: Application configuration
            db_service: Database service instance
            tidal_download_service: Optional Tidal download service
            tidal_session: Optional authenticated Tidal session
            dry_run: If True, don't make actual changes
        """
        self.config = config
        self.db_service = db_service
        self.tidal_download_service = tidal_download_service
        self.tidal_session = tidal_session
        self.dry_run = dry_run

        # Initialize components
        self.tidal_fetcher = TidalStateFetcher(db_service, tidal_session=tidal_session)
        playlists_root = Path(config.mp3_directory) / "Playlists"
        self.filesystem_scanner = FilesystemScanner(
            db_service, playlists_root=playlists_root
        )
        self.dedup_logic = DeduplicationLogic(db_service)
        self.decision_engine = SyncDecisionEngine(
            db_service,
            music_root=config.mp3_directory,
            target_format=config.target_audio_format,
            dedup_logic=self.dedup_logic,
        )
        self.download_orchestrator = DownloadOrchestrator(
            db_service=db_service,
            music_root=config.mp3_directory,
            deduplication_logic=self.dedup_logic,
            tidal_download_service=tidal_download_service,
            dry_run=dry_run,
        )

    def sync_all(
        self,
        fetch_tidal: bool = True,
        scan_filesystem: bool = True,
        analyze_deduplication: bool = True,
        stop_after_stage: SyncStage | None = None,
    ) -> SyncResult:
        """Execute complete sync operation.

        Args:
            fetch_tidal: Whether to fetch state from Tidal
            scan_filesystem: Whether to scan filesystem
            analyze_deduplication: Whether to analyze deduplication needs
            stop_after_stage: Stage after which to stop execution
                (defaults to execution)

        Returns:
            SyncResult with details of sync operation
        """
        result = SyncResult()
        requested_stage = stop_after_stage or SyncStage.EXECUTION
        result.stop_requested = requested_stage

        try:
            for stage in SyncStage.ordered():
                continue_run = self._execute_stage(
                    stage,
                    result,
                    fetch_tidal=fetch_tidal,
                    scan_filesystem=scan_filesystem,
                    analyze_deduplication=analyze_deduplication,
                )

                if not continue_run:
                    result.stopped_after = stage
                    break

                if requested_stage == stage:
                    result.stopped_after = stage
                    break

            if result.stopped_after is None:
                result.stopped_after = SyncStage.EXECUTION

            self._log_sync_summary(result)

            return result

        except Exception as e:
            self._handle_sync_error(result, e)
            return result

    def _execute_tidal_fetch_step(self, result: SyncResult) -> None:
        """Execute step 1: Fetch Tidal state."""
        logger.info("Step 1/5: Fetching state from Tidal...")
        result.tidal_fetch = self._fetch_tidal_state()
        self._collect_errors(result, result.tidal_fetch.errors, "Tidal fetch error")

    def _execute_filesystem_scan_step(self, result: SyncResult) -> None:
        """Execute step 2: Scan filesystem."""
        logger.info("Step 2/5: Scanning local filesystem...")
        result.filesystem_scan = self._scan_filesystem()
        self._collect_errors(
            result, result.filesystem_scan.errors, "Filesystem scan error"
        )

    def _execute_deduplication_step(self, result: SyncResult) -> None:
        """Execute step 3: Analyze deduplication."""
        logger.info("Step 3/5: Analyzing deduplication needs...")
        result.deduplication = self._analyze_deduplication()

    def _execute_decision_generation_step(self, result: SyncResult) -> bool:
        """Execute step 4: Generate sync decisions.

        Returns:
            True if decisions were generated successfully, False otherwise
        """
        logger.info("Step 4/5: Generating sync decisions...")
        result.decisions = self._generate_decisions()

        if not result.decisions:
            result.add_error("Failed to generate sync decisions")
            return False

        logger.info("Generated %d sync decisions", len(result.decisions.decisions))
        return True

    def _execute_decision_execution_step(self, result: SyncResult) -> None:
        """Execute step 5: Execute sync decisions."""
        logger.info("Step 5/5: Executing sync decisions...")
        # Type narrowing: decisions is guaranteed to exist (checked in caller)
        decisions = result.decisions
        if decisions is None:
            return

        result.execution = self._execute_decisions(decisions)
        self._collect_errors(result, result.execution.errors, "Execution error")

    def _execute_stage(
        self,
        stage: SyncStage,
        result: SyncResult,
        *,
        fetch_tidal: bool,
        scan_filesystem: bool,
        analyze_deduplication: bool,
    ) -> bool:
        """Execute a single stage.

        Returns False to halt further processing.
        """
        if stage == SyncStage.FETCH:
            if fetch_tidal:
                self._execute_tidal_fetch_step(result)
            else:
                logger.info(
                    "Step 1/5: Fetching state from Tidal... " "[skipped via --no-fetch]"
                )
            return True

        if stage == SyncStage.SCAN:
            if scan_filesystem:
                self._execute_filesystem_scan_step(result)
            else:
                logger.info(
                    "Step 2/5: Scanning local filesystem... " "[skipped via --no-scan]"
                )
            return True

        if stage == SyncStage.DEDUP:
            if analyze_deduplication:
                self._execute_deduplication_step(result)
            else:
                logger.info(
                    "Step 3/5: Analyzing deduplication needs... "
                    "[skipped via --no-dedup]"
                )
            return True

        if stage == SyncStage.DECISIONS:
            return self._execute_decision_generation_step(result)

        # All stages handled above
        if result.decisions:
            self._execute_decision_execution_step(result)
        else:
            logger.info(
                "Step 5/5: Executing sync decisions... "
                "[skipped - no decisions available]"
            )
        return True

    def _collect_errors(
        self, result: SyncResult, errors: List[str], prefix: str
    ) -> None:
        """Collect errors from a step and add them to the result."""
        if errors:
            for error in errors:
                result.add_error(f"{prefix}: {error}")

    def _log_sync_summary(self, result: SyncResult) -> None:
        """Log the sync operation summary."""
        summary = result.get_summary()
        logger.info("Sync complete: %s", summary)

    def _handle_sync_error(self, result: SyncResult, error: Exception) -> None:
        """Handle sync operation error."""
        error_msg = f"Sync operation failed: {str(error)}"
        result.add_error(error_msg)
        logger.exception(error_msg)

    def sync_playlist(self, playlist_name: str) -> SyncResult:
        """Sync a specific playlist.

        Args:
            playlist_name: Name of the playlist to sync

        Returns:
            SyncResult with details of sync operation
        """
        result = SyncResult()

        try:
            # Get playlist from database
            playlist = self.db_service.get_playlist_by_name(playlist_name)
            if not playlist:
                result.add_error(f"Playlist '{playlist_name}' not found in database")
                return result

            logger.info("Syncing playlist: %s", playlist_name)

            # Fetch Tidal state for this playlist
            logger.info("Step 1/5: Fetching playlist from Tidal...")
            result.tidal_fetch = self._fetch_tidal_state(playlist_ids=[playlist.id])

            # Scan filesystem for this playlist
            logger.info("Step 2/5: Scanning playlist directory...")
            result.filesystem_scan = self._scan_filesystem(
                playlist_filter=[playlist_name]
            )

            # Analyze deduplication for tracks in this playlist
            logger.info("Step 3/5: Analyzing deduplication...")
            result.deduplication = self._analyze_deduplication(
                playlist_ids=[playlist.id]
            )

            # Generate decisions for this playlist
            logger.info("Step 4/5: Generating sync decisions...")
            result.decisions = self._generate_decisions(playlist_ids=[playlist.id])

            # Execute decisions
            logger.info("Step 5/5: Executing sync decisions...")
            result.execution = self._execute_decisions(result.decisions)

            summary = result.get_summary()
            logger.info("Playlist sync complete: %s", summary)

            return result

        except Exception as e:
            error_msg = f"Playlist sync failed: {str(e)}"
            result.add_error(error_msg)
            logger.exception(error_msg)
            return result

    def _fetch_tidal_state(
        self, playlist_ids: List[int] | None = None
    ) -> FetchStatistics:
        """Fetch state from Tidal."""
        # Create statistics tracker
        stats = FetchStatistics()

        if playlist_ids:
            # Fetch specific playlists
            for playlist_id in playlist_ids:
                logger.info("Fetching playlist %d from Tidal", playlist_id)
                stats.playlists_fetched += 1
        else:
            # Fetch all playlists
            playlists = self.tidal_fetcher.fetch_all_playlists()
            stats.playlists_fetched = len(playlists)

        return stats

    def _scan_filesystem(
        self, playlist_filter: List[str] | None = None
    ) -> ScanStatistics:
        """Scan filesystem state."""
        # scan_all_playlists returns dict and updates internal _stats
        self.filesystem_scanner.scan_all_playlists()
        # Return the internal _stats object
        return self.filesystem_scanner._stats

    def _analyze_deduplication(
        self, playlist_ids: List[int] | None = None
    ) -> DeduplicationResult:
        """Analyze deduplication needs."""
        if playlist_ids:
            # Analyze specific playlists
            result = DeduplicationResult()
            for playlist_id in playlist_ids:
                # Get track associations for this playlist
                playlist_tracks = self.db_service.get_playlist_track_associations(
                    playlist_id
                )
                for pt in playlist_tracks:
                    if pt.track_id:
                        decision = self.dedup_logic.analyze_track_distribution(
                            pt.track_id
                        )
                        if decision:
                            result.decisions.append(decision)
            return result
        else:
            # Analyze all tracks
            return self.dedup_logic.analyze_all_tracks()

    def _generate_decisions(
        self, playlist_ids: List[int] | None = None
    ) -> SyncDecisions:
        """Generate sync decisions."""
        if playlist_ids:
            # Generate decisions for specific playlists
            decisions = SyncDecisions()
            for playlist_id in playlist_ids:
                playlist_decisions = self.decision_engine.analyze_playlist_sync(
                    playlist_id
                )
                for decision in playlist_decisions.decisions:
                    decisions.add_decision(decision)
            return decisions
        else:
            # Generate decisions for all playlists
            return self.decision_engine.analyze_all_playlists()

    def _execute_decisions(self, decisions: SyncDecisions) -> ExecutionResult:
        """Execute sync decisions."""
        return self.download_orchestrator.execute_decisions(
            decisions, target_format=self.config.target_audio_format
        )

    def ensure_directories(self) -> int:
        """Ensure all playlist directories exist.

        Returns:
            Number of directories created
        """
        return self.download_orchestrator.ensure_playlist_directories()
