"""Tidal integration module.

Handles interaction with Tidal API, downloading tracks, and managing Tidal state.
"""

from .api_client import TidalApiService, TidalConnectionError
from .download_service import TidalDownloadError, TidalDownloadService
from .snapshot_service import TidalSnapshotService
from .state_fetcher import FetchStatistics, TidalStateFetcher

__all__ = [
    "TidalApiService",
    "TidalConnectionError",
    "TidalDownloadService",
    "TidalDownloadError",
    "TidalStateFetcher",
    "FetchStatistics",
    "TidalSnapshotService",
]
