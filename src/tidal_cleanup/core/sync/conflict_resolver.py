"""Conflict resolution for sync operations.

This module handles edge cases and conflicts that can arise during sync operations:
- Concurrent file modifications
- File system race conditions
- Conflicting sync decisions
- Missing or corrupted files
"""

import logging
import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...database.service import DatabaseService
from .decision_engine import DecisionResult, SyncAction

logger = logging.getLogger(__name__)


class ConflictType(str, Enum):
    """Types of conflicts that can occur during sync."""

    # File system conflicts
    FILE_EXISTS = "file_exists"  # Target file already exists
    FILE_MISSING = "file_missing"  # Expected file is missing
    FILE_MODIFIED = "file_modified"  # File was modified during sync
    PERMISSION_DENIED = "permission_denied"  # Insufficient permissions

    # Decision conflicts
    DUPLICATE_DECISION = "duplicate_decision"  # Multiple decisions for same target
    CONFLICTING_ACTIONS = "conflicting_actions"  # Conflicting actions for same file

    # Race conditions
    CONCURRENT_MODIFICATION = "concurrent_modification"  # File changed during sync
    LOCK_TIMEOUT = "lock_timeout"  # Couldn't acquire file lock


class ConflictResolution(str, Enum):
    """Resolution strategies for conflicts."""

    SKIP = "skip"  # Skip the conflicting operation
    RETRY = "retry"  # Retry the operation
    OVERWRITE = "overwrite"  # Overwrite existing file
    BACKUP = "backup"  # Backup existing file and proceed
    MERGE = "merge"  # Merge changes (if possible)
    ABORT = "abort"  # Abort the entire operation
    USE_EXISTING = "use_existing"  # Use existing file/state


@dataclass
class Conflict:
    """Represents a conflict that occurred during sync."""

    conflict_type: ConflictType
    description: str
    decision: Optional[DecisionResult] = None
    file_path: Optional[Path] = None
    resolution: Optional[ConflictResolution] = None
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)

    def __str__(self) -> str:
        """String representation of conflict."""
        parts = [f"{self.conflict_type.value}: {self.description}"]
        if self.file_path:
            parts.append(f"(file: {self.file_path})")
        if self.resolution:
            parts.append(f"[resolved: {self.resolution.value}]")
        return " ".join(parts)


@dataclass
class ConflictResolutionResult:
    """Result of conflict resolution."""

    conflicts_detected: int = 0
    conflicts_resolved: int = 0
    conflicts_skipped: int = 0
    conflicts_failed: int = 0
    conflicts: List[Conflict] = dataclass_field(default_factory=list)

    def add_conflict(self, conflict: Conflict) -> None:
        """Add a conflict to the result."""
        self.conflicts.append(conflict)
        self.conflicts_detected += 1

        if conflict.resolution == ConflictResolution.SKIP:
            self.conflicts_skipped += 1
        elif conflict.resolution:
            self.conflicts_resolved += 1
        else:
            self.conflicts_failed += 1


class ConflictResolver:
    """Resolves conflicts during sync operations."""

    def __init__(
        self,
        db_service: DatabaseService,
        auto_resolve: bool = True,
        backup_conflicts: bool = True,
        max_retries: int = 3,
    ):
        """Initialize conflict resolver.

        Args:
            db_service: Database service for queries
            auto_resolve: Whether to automatically resolve conflicts
            backup_conflicts: Whether to backup files before overwriting
            max_retries: Maximum number of retries for failed operations
        """
        self.db_service = db_service
        self.auto_resolve = auto_resolve
        self.backup_conflicts = backup_conflicts
        self.max_retries = max_retries

    def check_file_conflicts(
        self, target_path: Path, action: SyncAction
    ) -> Optional[Conflict]:
        """Check for file system conflicts.

        Args:
            target_path: Target file path
            action: Sync action being performed

        Returns:
            Conflict if detected, None otherwise
        """
        # Check if target exists when it shouldn't
        if action == SyncAction.DOWNLOAD_TRACK and target_path.exists():
            return Conflict(
                conflict_type=ConflictType.FILE_EXISTS,
                description="File already exists at target location",
                file_path=target_path,
            )

        # Check permissions
        if target_path.exists():
            try:
                # Try to access the file
                target_path.stat()
            except PermissionError:
                return Conflict(
                    conflict_type=ConflictType.PERMISSION_DENIED,
                    description="Insufficient permissions to access file",
                    file_path=target_path,
                )

        return None

    def resolve_file_conflict(self, conflict: Conflict) -> ConflictResolution:
        """Resolve a file system conflict.

        Args:
            conflict: The conflict to resolve

        Returns:
            Resolution strategy
        """
        if not self.auto_resolve:
            return ConflictResolution.SKIP

        # Handle different conflict types
        if conflict.conflict_type == ConflictType.FILE_EXISTS:
            # For existing files, backup and overwrite
            if self.backup_conflicts:
                return ConflictResolution.BACKUP
            return ConflictResolution.OVERWRITE

        elif conflict.conflict_type == ConflictType.FILE_MISSING:
            # Missing file - try to download again
            return ConflictResolution.RETRY

        elif conflict.conflict_type == ConflictType.PERMISSION_DENIED:
            # Permission issues - skip
            logger.warning("Permission denied: %s", conflict.file_path)
            return ConflictResolution.SKIP

        elif conflict.conflict_type == ConflictType.CONCURRENT_MODIFICATION:
            # File modified during sync - retry
            return ConflictResolution.RETRY

        # Default: skip conflicting operations
        return ConflictResolution.SKIP

    def detect_decision_conflicts(
        self, decisions: List[DecisionResult]
    ) -> List[Conflict]:
        """Detect conflicts between sync decisions.

        Args:
            decisions: List of sync decisions

        Returns:
            List of conflicts detected
        """
        conflicts = []
        target_paths: dict[Path, List[DecisionResult]] = {}

        # Group decisions by target path
        for decision in decisions:
            if decision.target_path:
                target = Path(decision.target_path)
                if target not in target_paths:
                    target_paths[target] = []
                target_paths[target].append(decision)

        # Check for conflicting decisions
        for target, target_decisions in target_paths.items():
            if len(target_decisions) > 1:
                # Multiple decisions for same target
                actions = [d.action for d in target_decisions]
                if len(set(actions)) > 1:
                    # Different actions for same target
                    conflict = Conflict(
                        conflict_type=ConflictType.CONFLICTING_ACTIONS,
                        description=(
                            f"Multiple conflicting actions for same target: "
                            f"{actions}"
                        ),
                        file_path=target,
                        metadata={"decisions": target_decisions},
                    )
                    conflicts.append(conflict)
                else:
                    # Same action multiple times
                    conflict = Conflict(
                        conflict_type=ConflictType.DUPLICATE_DECISION,
                        description=(
                            f"Duplicate decision for target "
                            f"({len(target_decisions)} times)"
                        ),
                        file_path=target,
                        metadata={"decisions": target_decisions},
                    )
                    conflicts.append(conflict)

        return conflicts

    def resolve_decision_conflicts(
        self, conflicts: List[Conflict]
    ) -> List[DecisionResult]:
        """Resolve conflicts between decisions.

        Args:
            conflicts: List of conflicts to resolve

        Returns:
            List of resolved decisions
        """
        resolved_decisions = []

        for conflict in conflicts:
            decisions = conflict.metadata.get("decisions", [])

            if conflict.conflict_type == ConflictType.DUPLICATE_DECISION:
                # Keep only the first decision
                if decisions:
                    resolved_decisions.append(decisions[0])
                    conflict.resolution = ConflictResolution.USE_EXISTING
                    logger.info("Resolved duplicate decision: kept first decision")

            elif conflict.conflict_type == ConflictType.CONFLICTING_ACTIONS:
                # ! REMOVE MAGIC NUMBERS!
                # Prioritize destructive operations last to reduce risk
                priority = {
                    SyncAction.DOWNLOAD_TRACK: 4,
                    SyncAction.UPDATE_METADATA: 3,
                    SyncAction.VERIFY_FILE: 2,
                    SyncAction.REMOVE_FILE: 1,
                    SyncAction.NO_ACTION: 0,
                }

                highest_priority = max(
                    decisions,
                    key=lambda d: priority.get(d.action, -1),
                )
                resolved_decisions.append(highest_priority)
                conflict.resolution = ConflictResolution.USE_EXISTING
                logger.info(
                    f"Resolved conflicting actions: chose {highest_priority.action}"
                )

        return resolved_decisions

    def backup_file(self, file_path: Path) -> Optional[Path]:
        """Create a backup of a file.

        Args:
            file_path: Path to file to backup

        Returns:
            Path to backup file, or None if backup failed
        """
        import shutil

        if not file_path.exists():
            return None

        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = file_path.parent / f"{file_path.name}.backup_{timestamp}"

            shutil.copy2(file_path, backup_path)

            logger.info("Created backup: %s", backup_path)
            return backup_path

        except Exception as e:
            logger.error("Failed to create backup of %s: %s", file_path, e)
            return None

    def apply_resolution(
        self, conflict: Conflict, resolution: ConflictResolution
    ) -> bool:
        """Apply a resolution to a conflict.

        Args:
            conflict: The conflict to resolve
            resolution: Resolution strategy to apply

        Returns:
            True if resolution was successful, False otherwise
        """
        conflict.resolution = resolution

        try:
            if resolution == ConflictResolution.BACKUP and conflict.file_path:
                backup_path = self.backup_file(conflict.file_path)
                if backup_path:
                    conflict.metadata["backup_path"] = str(backup_path)
                    return True
                return False

            elif resolution == ConflictResolution.OVERWRITE and conflict.file_path:
                if conflict.file_path.exists():
                    conflict.file_path.unlink()
                return True

            elif resolution == ConflictResolution.SKIP:
                return True

            # Other resolutions are handled by caller
            return True

        except Exception as e:
            logger.error("Failed to apply resolution %s: %s", resolution, e)
            return False
