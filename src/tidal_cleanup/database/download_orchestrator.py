"""Download orchestrator for executing sync decisions.

This module coordinates the execution of sync decisions from SyncDecisionEngine,
handling downloads, symlink creation, and file operations.
"""

import logging
import os
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Dict, List

from ..services.tidal_download_service import (
    TidalDownloadError,
    TidalDownloadService,
)
from .conflict_resolver import ConflictResolver
from .deduplication_logic import DeduplicationLogic
from .models import DownloadStatus, Track
from .progress_tracker import ProgressCallback, ProgressPhase, ProgressTracker
from .service import DatabaseService
from .sync_decision_engine import DecisionResult, SyncAction, SyncDecisions

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing sync decisions."""

    decisions_executed: int = 0
    downloads_attempted: int = 0
    downloads_successful: int = 0
    downloads_failed: int = 0
    symlinks_created: int = 0
    symlinks_updated: int = 0
    symlinks_removed: int = 0
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
            "symlinks_created": self.symlinks_created,
            "symlinks_updated": self.symlinks_updated,
            "symlinks_removed": self.symlinks_removed,
            "files_removed": self.files_removed,
            "errors": len(self.errors),
        }


class DownloadOrchestrator:
    """Orchestrates execution of sync decisions.

    Coordinates downloading tracks, creating symlinks, and managing files based on
    decisions from SyncDecisionEngine and DeduplicationLogic.
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
        self.dedup_logic = deduplication_logic or DeduplicationLogic(
            db_service, strategy="first_alphabetically"
        )
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
            logger.warning(f"Detected {len(conflicts)} decision conflicts")
            # Resolve conflicts
            resolved = self.conflict_resolver.resolve_decision_conflicts(conflicts)
            logger.info(f"Resolved to {len(resolved)} decisions")

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
        elif decision.action == SyncAction.CREATE_SYMLINK:
            self._execute_create_symlink(decision, result)
        elif decision.action == SyncAction.UPDATE_SYMLINK:
            self._execute_update_symlink(decision, result)
        elif decision.action == SyncAction.REMOVE_SYMLINK:
            self._execute_remove_symlink(decision, result)
        elif decision.action == SyncAction.REMOVE_FILE:
            self._execute_remove_file(decision, result)
        elif decision.action == SyncAction.NO_ACTION:
            # Nothing to do
            pass
        else:
            logger.warning(f"Unhandled action type: {decision.action}")

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
        """Update track in database after successful download."""
        with self.db_service.get_session() as session:
            track_obj = session.merge(track)
            track_obj.download_status = DownloadStatus.DOWNLOADED
            track_obj.file_path = str(target_path)
            session.commit()

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

    def _execute_create_symlink(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Execute create symlink decision.

        Args:
            decision: Create symlink decision
            result: ExecutionResult to update
        """
        if not decision.source_path or not decision.target_path:
            result.add_error(
                f"Missing paths for symlink creation: "
                f"source={decision.source_path}, target={decision.target_path}"
            )
            return

        source = Path(decision.source_path)
        target = Path(decision.target_path)

        if self.dry_run:
            logger.info(f"DRY RUN: Would create symlink {source} -> {target}")
            result.symlinks_created += 1
            return

        try:
            # Ensure parent directory exists
            source.parent.mkdir(parents=True, exist_ok=True)

            # Remove existing file/symlink if it exists
            if source.exists() or source.is_symlink():
                source.unlink()

            # Create symlink
            os.symlink(target, source)
            result.symlinks_created += 1
            logger.info(f"Created symlink {source} -> {target}")

            # Update database
            if decision.playlist_track_id:
                self._update_symlink_in_db(
                    decision.playlist_track_id, str(source), True
                )

        except Exception as e:
            result.add_error(f"Failed to create symlink {source}: {str(e)}")

    def _execute_update_symlink(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Execute update symlink decision.

        Args:
            decision: Update symlink decision
            result: ExecutionResult to update
        """
        if not decision.source_path or not decision.target_path:
            result.add_error(
                f"Missing paths for symlink update: "
                f"source={decision.source_path}, target={decision.target_path}"
            )
            return

        source = Path(decision.source_path)
        target = Path(decision.target_path)

        if self.dry_run:
            logger.info(f"DRY RUN: Would update symlink {source} -> {target}")
            result.symlinks_updated += 1
            return

        try:
            # Remove existing symlink
            if source.exists() or source.is_symlink():
                source.unlink()

            # Create new symlink
            os.symlink(target, source)
            result.symlinks_updated += 1
            logger.info(f"Updated symlink {source} -> {target}")

            # Update database
            if decision.playlist_track_id:
                self._update_symlink_in_db(
                    decision.playlist_track_id, str(source), True
                )

        except Exception as e:
            result.add_error(f"Failed to update symlink {source}: {str(e)}")

    def _execute_remove_symlink(
        self, decision: DecisionResult, result: ExecutionResult
    ) -> None:
        """Execute remove symlink decision.

        Args:
            decision: Remove symlink decision
            result: ExecutionResult to update
        """
        if not decision.source_path:
            result.add_error("Missing source path for symlink removal")
            return

        source = Path(decision.source_path)

        if self.dry_run:
            logger.info(f"DRY RUN: Would remove symlink {source}")
            result.symlinks_removed += 1
            return

        try:
            if source.is_symlink():
                source.unlink()
                result.symlinks_removed += 1
                logger.info(f"Removed symlink {source}")

                # Update database
                if decision.playlist_track_id:
                    self._update_symlink_in_db(decision.playlist_track_id, None, None)
            else:
                logger.warning(f"Path is not a symlink: {source}")

        except Exception as e:
            result.add_error(f"Failed to remove symlink {source}: {str(e)}")

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
            logger.info(f"DRY RUN: Would remove file {source}")
            result.files_removed += 1
            return

        try:
            if source.exists():
                source.unlink()
                result.files_removed += 1
                logger.info(f"Removed file {source}")

                # Update database if track
                if decision.track_id:
                    self._update_track_file_path(decision.track_id, None)
            else:
                logger.warning(f"File does not exist: {source}")

        except Exception as e:
            result.add_error(f"Failed to remove file {source}: {str(e)}")

    def _update_symlink_in_db(
        self,
        playlist_track_id: int,
        symlink_path: str | None,
        symlink_valid: bool | None,
    ) -> None:
        """Update symlink information in database.

        Args:
            playlist_track_id: PlaylistTrack ID
            symlink_path: New symlink path or None
            symlink_valid: Whether symlink is valid or None
        """
        from .models import PlaylistTrack

        with self.db_service.get_session() as session:
            pt = session.get(PlaylistTrack, playlist_track_id)
            if pt:
                pt.symlink_path = symlink_path
                pt.symlink_valid = symlink_valid
                session.commit()

    def _update_track_file_path(self, track_id: int, file_path: str | None) -> None:
        """Update track file path in database.

        Args:
            track_id: Track ID
            file_path: New file path or None
        """
        track = self.db_service.get_track_by_id(track_id)
        if track:
            with self.db_service.get_session() as session:
                track_obj = session.merge(track)
                track_obj.file_path = file_path
                if file_path is None:
                    track_obj.download_status = DownloadStatus.NOT_DOWNLOADED
                session.commit()

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
                self.db_service.get_playlist_by_id(pid)
                for pid in playlist_ids
                if self.db_service.get_playlist_by_id(pid)
            ]

        created = 0
        for playlist in playlists:
            if not playlist:
                continue

            playlist_dir = self.playlists_root / playlist.name

            if not playlist_dir.exists():
                if self.dry_run:
                    logger.info(f"DRY RUN: Would create directory {playlist_dir}")
                    created += 1
                else:
                    playlist_dir.mkdir(parents=True, exist_ok=True)
                    created += 1
                    logger.info(f"Created playlist directory: {playlist_dir}")

        return created
