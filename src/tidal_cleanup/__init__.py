"""Tidal Playlist Cleanup Tool.

A modern tool for synchronizing and managing Tidal playlists with local audio files.
Provides functionality for track comparison, audio conversion, and Rekordbox XML.
"""

__version__ = "2.0.0"
__author__ = "Anton"
__email__ = ""
__all__ = [
    "Track",
    "Playlist",
    "Config",
    "TidalService",
    "FileService",
    "TrackComparisonService",
    "RekordboxService",
]

from .config import Config
from .models import Playlist, Track
from .services import (
    FileService,
    RekordboxService,
    TidalService,
    TrackComparisonService,
)

__all__ = [
    "Track",
    "Playlist",
    "Config",
    "TidalService",
    "FileService",
    "TrackComparisonService",
    "RekordboxService",
]
