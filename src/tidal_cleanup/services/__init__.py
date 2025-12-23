"""Services for the Tidal cleanup application.

DEPRECATED: This module is kept for backward compatibility only.
All services have been reorganized:
- Active services → core.tidal, core.rekordbox
- Legacy services → legacy module
"""

# Re-export from new locations for backward compatibility
from ..core.rekordbox import RekordboxGenerationError, RekordboxService
from ..core.tidal import (
    TidalApiService,
    TidalConnectionError,
    TidalDownloadError,
    TidalDownloadService,
)
from ..legacy import (
    DeletionMode,
    DirectoryDiff,
    DirectoryDiffService,
    FileIdentity,
    FileOperationError,
    FileService,
    PlaylistSynchronizer,
    TrackComparisonService,
)

__all__ = [
    "TidalApiService",
    "TidalConnectionError",
    "TidalDownloadService",
    "TidalDownloadError",
    "FileService",
    "FileOperationError",
    "TrackComparisonService",
    "RekordboxService",
    "RekordboxGenerationError",
    "PlaylistSynchronizer",
    "DeletionMode",
    "DirectoryDiffService",
    "DirectoryDiff",
    "FileIdentity",
]
