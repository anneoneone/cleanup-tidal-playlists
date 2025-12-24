"""CLI command modules."""

from .database import db
from .diff import diff_command
from .download import download
from .init import check_all_services, init_command
from .legacy import TidalCleanupApp, legacy_convert, legacy_full, legacy_sync, status
from .rekordbox import rekordbox
from .rekordbox_sync import sync_rekordbox_command
from .sync import sync_command

__all__ = [
    "TidalCleanupApp",
    "legacy_sync",
    "legacy_convert",
    "rekordbox",
    "status",
    "legacy_full",
    "download",
    "db",
    "init_command",
    "check_all_services",
    "diff_command",
    "sync_rekordbox_command",
    "sync_command",
]
