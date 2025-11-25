"""Legacy services module.

Contains deprecated services that will be removed in future versions. These services are
only used by legacy CLI commands.
"""

from .directory_diff import DirectoryDiff, DirectoryDiffService, FileIdentity
from .file_service import FileOperationError, FileService
from .playlist_synchronizer import DeletionMode, PlaylistSynchronizer
from .track_comparison import TrackComparisonService

__all__ = [
    "FileService",
    "FileOperationError",
    "TrackComparisonService",
    "PlaylistSynchronizer",
    "DeletionMode",
    "DirectoryDiffService",
    "DirectoryDiff",
    "FileIdentity",
]
