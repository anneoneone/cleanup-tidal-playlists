"""Download orchestrator for executing sync decisions.

This module coordinates the execution of sync decisions from SyncDecisionEngine,
handling downloads and file operations for playlist-specific storage.
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from ...database.models import DownloadStatus, Track
from ...database.progress_tracker import (
    ProgressCallback,
    ProgressPhase,
    ProgressTracker,
)
from ...database.service import DatabaseService
from ..tidal.download_service import (
    TidalDownloadError,
    TidalDownloadService,
)
from .conflict_resolver import ConflictResolver
from .decision_engine import DecisionResult, SyncAction, SyncDecisions
from .deduplication import DeduplicationLogic

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing sync decisions."""

    decisions_executed: int = 0
    downloads_attempted: int = 0
    downloads_successful: int = 0
    downloads_failed: int = 0
    files_removed: int = 0
    errors: List[str] = dataclass_field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        logger.error(error)

    def get_summary(self) -> Dict[str, int]:
        """Get summary statistics."""
        return {
            "decisions_executed": self.decisions_executed,
            "downloads_attempted": self.downloads_attempted,
            "downloads_successful": self.downloads_successful,
            "downloads_failed": self.downloads_failed,
            "files_removed": self.files_removed,
            "errors": len(self.errors),
        }


class DownloadOrchestrator:
    """Orchestrates execution of sync decisions.

    Coordinates downloading tracks and managing files based on decisions from
    SyncDecisionEngine and DeduplicationLogic.
    """

    def __init__(
        self,
        db_service: DatabaseService,
        music_root: Path | str,
        deduplication_logic: DeduplicationLogic | None = None,
        download_service: TidalDownloadService | None = None,
        dry_run: bool = False,
        progress_callback: ProgressCallback | None = None,
        conflict_resolver: ConflictResolver | None = None,
    ):
        """Initialize download orchestrator.

        Args:
            db_service: Database service instance
            music_root: Root directory for music files (contains Playlists/)
            deduplication_logic: Logic for determining primary file locations
            download_service: Tidal download service for downloading tracks
            dry_run: If True, don't actually make changes, just log what would happen
            progress_callback: Optional callback for progress updates
            conflict_resolver: Optional conflict resolver (default: auto-resolve)
        """
        self.db_service = db_service
        self.music_root = Path(music_root)
        self.playlists_root = self.music_root / "Playlists"
        self.library_root = self.music_root
        self.dedup_logic = deduplication_logic or DeduplicationLogic(db_service)
        self.download_service = download_service
        self.dry_run = dry_run
        self.progress_tracker = ProgressTracker(callback=progress_callback)
        self.conflict_resolver = conflict_resolver or ConflictResolver(
            db_service, auto_resolve=True
        )

    def execute_decisions(
        self, decisions: SyncDecisions, target_format: str = "mp3"
    ) -> ExecutionResult:
        """Execute sync decisions.

        Args:
            decisions: SyncDecisions object with decisions to execute
            target_format: Target audio format for conversion (e.g., "mp3", "flac")

        Returns:
            ExecutionResult with execution statistics
        """
        result = ExecutionResult()
        self.target_format = target_format  # Store for use in _execute_download

        # Detect conflicts between decisions
        conflicts = self.conflict_resolver.detect_decision_conflicts(
            decisions.decisions
        )
        if conflicts:
            logger.warning("Detected %d decision conflicts", len(conflicts))
            # Resolve conflicts
            resolved = self.conflict_resolver.resolve_decision_conflicts(conflicts)
            logger.info("Resolved to %d decisions", len(resolved))

        # Get prioritized decisions
        prioritized = sorted(
            decisions.decisions, key=lambda d: d.priority, reverse=True
        )

        # Start progress tracking
        self.progress_tracker.start(
            ProgressPhase.EXECUTING_DECISIONS,
            len(prioritized),
            "Executing sync decisions",
        )

        for i, decision in enumerate(prioritized):
            try:
                self._execute_decision(decision, result)
                result.decisions_executed += 1
                self.progress_tracker.update(i + 1, f"Executed {decision.action}")
            except Exception as e:
                result.add_error(
                    f"Error executing decision {decision.action}: {str(e)}"
                )
                logger.exception(f"Decision execution failed: {decision.action}")

        self.progress_tracker.complete("Decisions executed")
        return result

    def _execute_decision(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Execute a single decision.

        Args:
            decision: DecisionResult to execute
            result: ExecutionResult to update with results
        """
        if decision.action == SyncAction.DOWNLOAD_TRACK:
            self._execute_download(decision, result)
        elif decision.action == SyncAction.REMOVE_FILE:
            self._execute_remove_file(decision, result)
        elif decision.action == SyncAction.NO_ACTION:
            # Nothing to do
            pass
        else:
            logger.warning("Unhandled action type: %s", decision.action)

    def _execute_download(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Execute a download decision.

        Args:
            decision: Download decision
            result: ExecutionResult to update
        """
        result.downloads_attempted += 1

        if self.dry_run:
            self._handle_dry_run_download(decision, result)
            return

        # Validate decision
        if not self._validate_download_decision(decision, result):
            return

        # Type narrowing: track_id is guaranteed to be int here (validated above)
        track_id = decision.track_id
        if track_id is None:  # Defensive check
            return

        try:
            # Get track from database
            track = self.db_service.get_track_by_id(track_id)
            if not track:
                result.downloads_failed += 1
                result.add_error(f"Track {decision.track_id} not found in database")
                return

            # Mark as downloading
            self._update_track_status(track, DownloadStatus.DOWNLOADING)

            logger.info(
                f"Downloading track {decision.track_id} to {decision.target_path}"
            )

            # Download the track using TidalDownloadService if available
            if self.download_service:
                self._perform_download(track, decision, result)
            else:
                self._handle_no_download_service(result)

        except Exception as e:
            result.downloads_failed += 1
            result.add_error(f"Failed to download track: {str(e)}")

    def _handle_dry_run_download(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Handle dry run mode for downloads."""
        logger.info(
            f"DRY RUN: Would download track {decision.track_id} "
            f"to {decision.target_path}"
        )
        result.downloads_successful += 1

    def _validate_download_decision(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> bool:
        """Validate download decision has required fields.

        Returns:
            True if valid, False otherwise
        """
        if decision.track_id is None:
            result.downloads_failed += 1
            error_msg = (
                f"Cannot download track: track_id is None "
                f"(reason: {decision.reason})"
            )
            result.add_error(error_msg)
            return False

        if not decision.target_path:
            result.downloads_failed += 1
            error_msg = (
                f"Cannot download track {decision.track_id}: "
                f"target_path is None (reason: {decision.reason})"
            )
            result.add_error(error_msg)
            return False

        return True

    def _update_track_status(self, track: Track, status: DownloadStatus) -> None:
        """Update track download status in database."""
        with self.db_service.get_session() as session:
            track_obj = session.merge(track)
            track_obj.download_status = status
            session.commit()

    def _perform_download(
        self, track: Track, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Perform the actual download and conversion using TidalDownloadService."""
        import subprocess  # noqa: S404

        try:
            # Type narrowing: target_path is guaranteed to be str here (validated above)
            target_path_str = decision.target_path
            if target_path_str is None:  # Defensive check
                raise ValueError("target_path is None")
            target_path = Path(target_path_str)
            tidal_track_id = self._get_tidal_track_id(track)

            # Type narrowing: download_service guaranteed to exist
            download_service = self.download_service
            if download_service is None:  # Defensive check
                raise ValueError("download_service is None")

            # Download track in original format (M4A)
            # Returns the actual path where file was downloaded
            actual_downloaded_path = download_service.download_track(
                track_id=tidal_track_id, target_path=target_path
            )

            # Convert to target format if not already in target format
            target_format = getattr(self, "target_format", "mp3")
            target_ext = f".{target_format.lower().replace('.', '')}"

            if actual_downloaded_path.suffix.lower() != target_ext:
                # Create converted file path in the desired target location
                converted_path = target_path.with_suffix(target_ext)

                # Ensure target directory exists
                converted_path.parent.mkdir(parents=True, exist_ok=True)

                # Run ffmpeg conversion
                cmd = [
                    "ffmpeg",
                    "-i",
                    str(actual_downloaded_path),
                    "-q:a",
                    "2",  # Quality setting
                    "-y",  # Overwrite output file
                    str(converted_path),
                ]

                subprocess.run(  # noqa: S603
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )

                # Remove original file after successful conversion
                actual_downloaded_path.unlink()

                # Update target_path to converted file
                target_path = converted_path
                logger.info(
                    f"Downloaded and converted track {decision.track_id} to "
                    f"{target_format.upper()} at {converted_path}"
                )
            else:
                # If already in target format, move to target location if different
                if actual_downloaded_path != target_path:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    actual_downloaded_path.rename(target_path)
                    logger.info(
                        f"Downloaded track {decision.track_id} at {target_path}"
                    )
                else:
                    target_path = actual_downloaded_path
                    logger.info(
                        f"Downloaded track {decision.track_id} at {target_path}"
                    )

            # Update database with success
            self._update_track_after_download(track, target_path)

            result.downloads_successful += 1

        except (TidalDownloadError, ValueError, subprocess.CalledProcessError) as e:
            self._handle_download_failure(track, decision, result, e)

    def _get_tidal_track_id(self, track: Track) -> int:
        """Get Tidal track ID from track object.

        Raises:
            ValueError: If track has no tidal_id
        """
        tidal_track_id = int(track.tidal_id) if track.tidal_id else None
        if tidal_track_id is None:
            raise ValueError(f"Track {track.id} has no tidal_id")
        return tidal_track_id

    def _update_track_after_download(self, track: Track, target_path: Path) -> None:
        """Update track metadata and relative paths after a download."""
        relative_path = self._to_library_relative_path(target_path)

        # Collect filesystem metadata when available
        file_size = None
        last_modified = None
        try:
            stat_result = target_path.stat()
            file_size = stat_result.st_size
            last_modified = datetime.fromtimestamp(
                stat_result.st_mtime, tz=timezone.utc
            )
        except OSError:
            logger.debug("Unable to stat downloaded file: %s", target_path)

        file_format = target_path.suffix.lstrip(".").lower() or None

        self.db_service.add_file_path_to_track(track.id, relative_path)
        self.db_service.update_track(
            track.id,
            {
                "download_status": DownloadStatus.DOWNLOADED.value,
                "downloaded_at": datetime.now(timezone.utc),
                "file_size_bytes": file_size,
                "file_last_modified": last_modified,
                "file_format": file_format,
            },
        )

    def _handle_download_failure(
        self,
        track: Track,
        decision: DecisionResult,
        result: ExecutionResult,
        error: Exception,
    ) -> None:
        """Handle download failure by updating database and result."""
        self._update_track_status(track, DownloadStatus.ERROR)
        result.downloads_failed += 1
        result.add_error(f"Failed to download track {decision.track_id}: {str(error)}")

    def _handle_no_download_service(self, result: ExecutionResult) -> None:
        """Handle case where no download service is configured."""
        logger.warning("No download service configured, marking as downloading only")
        result.downloads_successful += 1

    def _execute_remove_file(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Execute remove file decision.

        Args:
            decision: Remove file decision
            result: ExecutionResult to update
        """
        if not decision.source_path:
            result.add_error("Missing source path for file removal")
            return

        source = Path(decision.source_path)

        if self.dry_run:
            logger.info("DRY RUN: Would remove file %s", source)
            result.files_removed += 1
            return

        try:
            removed = False
            if source.exists():
                source.unlink()
                removed = True
                logger.info("Removed file %s", source)
            else:
                logger.warning("File does not exist: %s", source)

            if removed:
                result.files_removed += 1
                if decision.track_id:
                    self._remove_track_file_reference(decision.track_id, source)

        except Exception as e:
            result.add_error(f"Failed to remove file {source}: {str(e)}")

    def _remove_track_file_reference(self, track_id: int, file_path: Path) -> None:
        """Remove a file reference from a track's file_paths list."""
        relative_path = self._to_library_relative_path(file_path)
        try:
            self.db_service.remove_file_path_from_track(track_id, relative_path)
            track = self.db_service.get_track_by_id(track_id)
            if track and (not track.file_paths):
                self.db_service.update_track(
                    track_id,
                    {"download_status": DownloadStatus.NOT_DOWNLOADED.value},
                )
        except Exception as exc:
            logger.warning(
                "Failed to update file references for track %s: %s", track_id, exc
            )

    def _to_library_relative_path(self, path: Path) -> str:
        """Return a path relative to the music library root when possible."""
        try:
            return str(path.relative_to(self.library_root))
        except ValueError:
            return str(path)

    def ensure_playlist_directories(self, playlist_ids: List[int] | None = None) -> int:
        """Ensure playlist directories exist.

        Args:
            playlist_ids: List of playlist IDs to create directories for,
                         or None to create for all playlists

        Returns:
            Number of directories created
        """
        if playlist_ids is None:
            playlists = self.db_service.get_all_playlists()
        else:
            playlists = [
                pl
                for pid in playlist_ids
                if (pl := self.db_service.get_playlist_by_id(pid)) is not None
            ]

        created = 0
        for playlist in playlists:
            if not playlist:
                continue

            playlist_dir = self.playlists_root / playlist.name

            if not playlist_dir.exists():
                if self.dry_run:
                    logger.info("DRY RUN: Would create directory %s", playlist_dir)
                    created += 1
                else:
                    playlist_dir.mkdir(parents=True, exist_ok=True)
                    created += 1
                    logger.info("Created playlist directory: %s", playlist_dir)

        return created
