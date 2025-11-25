"""Filesystem module.

Handles scanning and managing local audio files.
"""

from .file_scanner import FileScannerService
from .scanner import FilesystemScanner, ScanStatistics

__all__ = [
    "FilesystemScanner",
    "ScanStatistics",
    "FileScannerService",
]
