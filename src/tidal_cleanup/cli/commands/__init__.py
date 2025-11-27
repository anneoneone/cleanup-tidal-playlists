"""CLI command modules."""

from .database import db
from .download import download
from .legacy import TidalCleanupApp, legacy_convert, legacy_full, legacy_sync, status
from .rekordbox import rekordbox

__all__ = [
    "TidalCleanupApp",
    "legacy_sync",
    "legacy_convert",
    "rekordbox",
    "status",
    "legacy_full",
    "download",
    "db",
]
