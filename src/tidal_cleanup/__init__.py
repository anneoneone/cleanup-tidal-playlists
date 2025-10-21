"""Tidal Playlist Cleanup Tool.

A modern tool for synchronizing and managing Tidal playlists with local audio files.
Provides functionality for track comparison, audio conversion, and Rekordbox XML.
"""

__version__ = "2.0.0"
__author__ = "Anton"
__email__ = ""

from .models import Track, Playlist
from .config import Config
from .services import (
    TidalService,
    FileService,
    TrackComparisonService,
    RekordboxService,
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
