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

from .deduplication_logic import DeduplicationLogic
from .models import DownloadStatus
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
        dry_run: bool = False,
    ):
        """Initialize download orchestrator.

        Args:
            db_service: Database service instance
            music_root: Root directory for music files (contains Playlists/)
            deduplication_logic: Logic for determining primary file locations
            dry_run: If True, don't actually make changes, just log what would happen
        """
        self.db_service = db_service
        self.music_root = Path(music_root)
        self.playlists_root = self.music_root / "Playlists"
        self.dedup_logic = deduplication_logic or DeduplicationLogic(
            db_service, strategy="first_alphabetically"
        )
        self.dry_run = dry_run

    def execute_decisions(self, decisions: SyncDecisions) -> ExecutionResult:
        """Execute sync decisions.

        Args:
            decisions: SyncDecisions object with decisions to execute

        Returns:
            ExecutionResult with execution statistics
        """
        result = ExecutionResult()

        # Get prioritized decisions
        prioritized = sorted(
            decisions.decisions, key=lambda d: d.priority, reverse=True
        )

        for decision in prioritized:
            try:
                self._execute_decision(decision, result)
                result.decisions_executed += 1
            except Exception as e:
                result.add_error(
                    f"Error executing decision {decision.action}: {str(e)}"
                )

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
            logger.info(
                f"DRY RUN: Would download track {decision.track_id} "
                f"to {decision.target_path}"
            )
            result.downloads_successful += 1
            return

        # For now, just mark as attempted and update status
        # Actual download implementation would use TidalDownloadService
        logger.info(
            f"Download requested for track {decision.track_id} "
            f"to {decision.target_path}"
        )

        # For now, just update the database to mark download as attempted
        if decision.track_id is None:
            result.downloads_failed += 1
            result.add_error("Cannot download track: track_id is None")
            return

        try:
            track = self.db_service.get_track_by_id(decision.track_id)
            if track:
                with self.db_service.get_session() as session:
                    track_obj = session.merge(track)
                    track_obj.download_status = DownloadStatus.DOWNLOADING
                    session.commit()
                result.downloads_successful += 1
                logger.info(f"Marked track {decision.track_id} as downloading")
        except Exception as e:
            result.downloads_failed += 1
            result.add_error(f"Failed to update download status: {str(e)}")

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
