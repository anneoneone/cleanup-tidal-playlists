"""Database package for playlist and track synchronization."""

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
from .service import DatabaseService
from .sync_decision_engine import (
    DecisionResult,
    SyncAction,
    SyncDecisionEngine,
    SyncDecisions,
)
from .sync_state import Change, ChangeType, SyncState, SyncStateComparator
from .tidal_snapshot_service import TidalSnapshotService
from .tidal_state_fetcher import TidalStateFetcher

__all__ = [
    "Track",
    "Playlist",
    "PlaylistTrack",
    "SyncOperation",
    "SyncSnapshot",
    "DatabaseService",
    "Change",
    "ChangeType",
    "SyncState",
    "SyncStateComparator",
    "TidalSnapshotService",
    "TidalStateFetcher",
    "FileScannerService",
    "FilesystemScanner",
    "DecisionResult",
    "SyncAction",
    "SyncDecisionEngine",
    "SyncDecisions",
    "DeduplicationLogic",
    "DeduplicationResult",
    "PrimaryFileDecision",
    "DownloadOrchestrator",
    "ExecutionResult",
    "DownloadStatus",
    "PlaylistSyncStatus",
    "TrackSyncStatus",
]
