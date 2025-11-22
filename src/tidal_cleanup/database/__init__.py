"""Database package for playlist and track synchronization."""

from .conflict_resolver import (
    Conflict,
    ConflictResolution,
    ConflictResolutionResult,
    ConflictResolver,
    ConflictType,
)
from .deduplication_logic import (
    DeduplicationLogic,
    DeduplicationResult,
    PrimaryFileDecision,
)
from .download_orchestrator import DownloadOrchestrator, ExecutionResult
from .file_scanner_service import FileScannerService
from .filesystem_scanner import FilesystemScanner
from .models import (
    DownloadStatus,
    Playlist,
    PlaylistSyncStatus,
    PlaylistTrack,
    SyncOperation,
    SyncSnapshot,
    Track,
    TrackSyncStatus,
)
from .progress_tracker import (
    ConsoleProgressReporter,
    ProgressCallback,
    ProgressPhase,
    ProgressTracker,
    ProgressUpdate,
    TqdmProgressReporter,
)
from .service import DatabaseService
from .sync_decision_engine import (
    DecisionResult,
    SyncAction,
    SyncDecisionEngine,
    SyncDecisions,
)
from .sync_orchestrator import SyncOrchestrator, SyncResult
from .sync_state import Change, ChangeType, SyncState, SyncStateComparator
from .tidal_snapshot_service import TidalSnapshotService
from .tidal_state_fetcher import TidalStateFetcher

__all__ = [
    # Models
    "Track",
    "Playlist",
    "PlaylistTrack",
    "SyncOperation",
    "SyncSnapshot",
    # Core services
    "DatabaseService",
    "FileScannerService",
    "FilesystemScanner",
    # Sync state
    "Change",
    "ChangeType",
    "SyncState",
    "SyncStateComparator",
    "TidalSnapshotService",
    "TidalStateFetcher",
    # Decision engine
    "DecisionResult",
    "SyncAction",
    "SyncDecisionEngine",
    "SyncDecisions",
    # Deduplication
    "DeduplicationLogic",
    "DeduplicationResult",
    "PrimaryFileDecision",
    # Orchestration
    "DownloadOrchestrator",
    "ExecutionResult",
    "SyncOrchestrator",
    "SyncResult",
    # Conflict resolution
    "Conflict",
    "ConflictType",
    "ConflictResolution",
    "ConflictResolver",
    "ConflictResolutionResult",
    # Progress tracking
    "ProgressTracker",
    "ProgressPhase",
    "ProgressUpdate",
    "ProgressCallback",
    "ConsoleProgressReporter",
    "TqdmProgressReporter",
    # Status
    "DownloadStatus",
    "PlaylistSyncStatus",
    "TrackSyncStatus",
]
