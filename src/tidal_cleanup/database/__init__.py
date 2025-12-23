"""Database package for playlist and track synchronization.

This package now only contains the pure database layer (service, models, progress
tracking). Business logic has been moved to core/ modules.
"""

# Pure database layer
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

# Note: Removed re-exports from core modules to avoid circular imports.
# Import directly from core modules instead:
# - from tidal_cleanup.core.tidal import TidalApiService, TidalStateFetcher, etc.
# - from tidal_cleanup.core.filesystem import FilesystemScanner, etc.
# - from tidal_cleanup.core.sync import SyncDecisionEngine, etc.

__all__ = [
    # Models
    "Track",
    "Playlist",
    "PlaylistTrack",
    "SyncOperation",
    "SyncSnapshot",
    # Database service
    "DatabaseService",
    # Progress tracking
    "ProgressTracker",
    "ProgressPhase",
    "ProgressUpdate",
    "ProgressCallback",
    "ConsoleProgressReporter",
    "TqdmProgressReporter",
    # Status enums
    "DownloadStatus",
    "PlaylistSyncStatus",
    "TrackSyncStatus",
]
