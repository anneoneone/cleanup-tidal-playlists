"""Filesystem scanner for unified Tidal-Filesystem sync.

This service scans the mp3/Playlists/* directories to identify what files
currently exist on the filesystem, validates symlinks, and updates the database
with the current filesystem state. It's the second step in the unified sync
workflow: Tidal fetch → Filesystem scan → Compare → Sync.
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from tidal_cleanup.database.models import DownloadStatus
from tidal_cleanup.database.service import DatabaseService

logger = logging.getLogger(__name__)


@dataclass
class ScanStatistics:
    """Statistics from filesystem scan operation."""

    playlists_scanned: int = 0
    files_found: int = 0
    symlinks_found: int = 0
    symlinks_valid: int = 0
    symlinks_broken: int = 0
    tracks_updated: int = 0
    playlist_tracks_updated: int = 0
    errors: List[str] = dataclass_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary format.

        Returns:
            Dictionary with statistics and limited error list
        """
        return {
            "playlists_scanned": self.playlists_scanned,
            "files_found": self.files_found,
            "symlinks_found": self.symlinks_found,
            "symlinks_valid": self.symlinks_valid,
            "symlinks_broken": self.symlinks_broken,
            "tracks_updated": self.tracks_updated,
            "playlist_tracks_updated": self.playlist_tracks_updated,
            "error_count": len(self.errors),
            "errors": self.errors[:10],  # Limit to first 10 errors
        }


class FilesystemScanner:
    """Scans filesystem for playlists and tracks, updates database."""

    def __init__(
        self,
        db_service: DatabaseService,
        playlists_root: Path,
        supported_extensions: tuple[str, ...] = (".mp3", ".flac", ".m4a", ".wav"),
    ) -> None:
        """Initialize filesystem scanner.

        Args:
            db_service: Database service instance
            playlists_root: Root directory for playlists (e.g., mp3/Playlists)
            supported_extensions: Tuple of supported audio file extensions
        """
        self.db_service = db_service
        self.playlists_root = Path(playlists_root)
        self.supported_extensions = supported_extensions
        self._stats = ScanStatistics()

    def scan_all_playlists(self) -> Dict[str, Any]:
        """Scan all playlist directories and update database.

        Returns:
            Dictionary with scan statistics

        Raises:
            RuntimeError: If playlists root directory doesn't exist
        """
        if not self.playlists_root.exists():
            raise RuntimeError(
                f"Playlists root directory does not exist: {self.playlists_root}"
            )

        # Reset statistics for new scan
        self._stats = ScanStatistics()

        logger.info("Scanning playlists from: %s", self.playlists_root)

        # Get all playlist directories
        playlist_dirs = self._find_playlist_directories()
        logger.info("Found %d playlist directories", len(playlist_dirs))

        # Process each playlist directory
        for playlist_dir in playlist_dirs:
            self._process_playlist_directory(playlist_dir)

        # Log summary
        self._log_scan_summary()

        return self._stats.to_dict()

    def _find_playlist_directories(self) -> List[Path]:
        """Find all playlist directories under playlists root.

        Returns:
            List of playlist directory paths
        """
        playlist_dirs: List[Path] = []

        for item in self.playlists_root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                playlist_dirs.append(item)

        return sorted(playlist_dirs)

    def _process_playlist_directory(self, playlist_dir: Path) -> None:
        """Process a single playlist directory.

        Args:
            playlist_dir: Path to playlist directory
        """
        try:
            playlist_name = playlist_dir.name
            logger.debug("Processing playlist directory: %s", playlist_name)

            # Get or create playlist in database
            playlist = self.db_service.get_playlist_by_name(playlist_name)

            if not playlist:
                logger.warning(
                    f"Playlist '{playlist_name}' not found in database, skipping"
                )
                self._stats.playlists_scanned += 1
                return

            # Find all audio files in playlist directory
            files = self._find_audio_files(playlist_dir)
            logger.debug("Found %d files in %s", len(files), playlist_name)

            # Process each file
            for file_path in files:
                self._process_file(playlist, file_path)

            self._stats.playlists_scanned += 1

        except Exception as e:
            error_msg = (
                f"Error processing playlist directory '{playlist_dir.name}': {e}"
            )
            logger.error(error_msg)
            self._stats.errors.append(error_msg)

    def _find_audio_files(self, directory: Path) -> List[Path]:
        """Find all audio files in directory (non-recursive).

        Args:
            directory: Directory to search

        Returns:
            List of audio file paths
        """
        audio_files: List[Path] = []

        for item in directory.iterdir():
            if (
                item.is_file() or item.is_symlink()
            ) and item.suffix.lower() in self.supported_extensions:
                audio_files.append(item)

        return sorted(audio_files)

    def _process_file(self, playlist: Any, file_path: Path) -> None:
        """Process a single file (regular file or symlink).

        Args:
            playlist: Playlist database object
            file_path: Path to file
        """
        try:
            is_symlink = file_path.is_symlink()

            if is_symlink:
                self._process_symlink(playlist, file_path)
            else:
                self._process_regular_file(playlist, file_path)

        except Exception as e:
            error_msg = f"Error processing file '{file_path.name}': {e}"
            logger.error(error_msg)
            self._stats.errors.append(error_msg)

    def _process_symlink(self, playlist: Any, symlink_path: Path) -> None:
        """Process a symlink file.

        Args:
            playlist: Playlist database object
            symlink_path: Path to symlink
        """
        self._stats.symlinks_found += 1

        # Validate symlink
        is_valid, target_path = self._validate_symlink(symlink_path)

        if is_valid:
            self._stats.symlinks_valid += 1
        else:
            self._stats.symlinks_broken += 1
            logger.warning("Broken symlink: %s", symlink_path)

        # Try to match file to a track
        target = target_path if is_valid else None
        track = self._match_file_to_track(symlink_path, target)

        if track:
            # Update symlink information
            result = self.db_service.update_symlink_status(
                playlist.id,
                track.id,
                str(symlink_path),
                is_valid,
            )
            if result:
                self._stats.playlist_tracks_updated += 1
                logger.debug(
                    f"Updated symlink status for track {track.id} "
                    f"in playlist {playlist.id}"
                )

    def _process_regular_file(self, playlist: Any, file_path: Path) -> None:
        """Process a regular (non-symlink) file.

        Args:
            playlist: Playlist database object
            file_path: Path to file
        """
        self._stats.files_found += 1

        # Try to match file to a track
        track = self._match_file_to_track(file_path, None)

        if track:
            # Update track file information
            file_stat = file_path.stat()

            update_data = {
                "file_path": str(file_path.relative_to(self.playlists_root.parent)),
                "file_size_bytes": file_stat.st_size,
                "file_last_modified": datetime.fromtimestamp(file_stat.st_mtime),
                "download_status": DownloadStatus.DOWNLOADED.value,
            }

            self.db_service.update_track(track.id, update_data)
            self._stats.tracks_updated += 1

            # Mark as primary in this playlist
            result = self.db_service.mark_playlist_track_as_primary(
                playlist.id, track.id
            )
            if result:
                self._stats.playlist_tracks_updated += 1

    def _validate_symlink(self, symlink_path: Path) -> tuple[bool, Path | None]:
        """Validate a symlink and get its target.

        Args:
            symlink_path: Path to symlink

        Returns:
            Tuple of (is_valid, target_path)
        """
        # Check if it's actually a symlink
        if not symlink_path.is_symlink():
            return False, None

        try:
            # Get the target path
            target_path = symlink_path.resolve()

            # Check if target exists
            if target_path.exists() and target_path.is_file():
                return True, target_path
            else:
                # Return the target path even if broken (for debugging)
                return False, target_path

        except (OSError, RuntimeError) as e:
            logger.debug("Error validating symlink %s: %s", symlink_path, e)
            return False, None

    def _match_file_to_track(
        self, file_path: Path, target_path: Path | None
    ) -> Any | None:
        """Match a file to a database track.

        Uses filename-based matching for now. Future: metadata, ISRC, etc.

        Args:
            file_path: Path to file (symlink or regular)
            target_path: Path to symlink target (if symlink)

        Returns:
            Matched Track object or None
        """
        # Extract filename without extension
        filename = file_path.stem

        # Try to parse filename as "Artist - Title"
        if " - " in filename:
            parts = filename.split(" - ", 1)
            if len(parts) == 2:
                artist, title = parts
                normalized_name = f"{artist.lower().strip()} - {title.lower().strip()}"

                # Find track by normalized name
                track = self.db_service.find_track_by_normalized_name(normalized_name)
                if track:
                    return track

        # Fallback: search by filename only
        all_tracks = self.db_service.get_all_tracks()
        for track in all_tracks:
            if track.normalized_name and filename.lower() in track.normalized_name:
                return track

        logger.debug("Could not match file to track: %s", file_path.name)
        return None

    def _log_scan_summary(self) -> None:
        """Log summary of scan operation."""
        logger.info(
            f"Filesystem scan complete: "
            f"{self._stats.playlists_scanned} playlists scanned, "
            f"{self._stats.files_found} files found, "
            f"{self._stats.symlinks_found} symlinks found "
            f"({self._stats.symlinks_valid} valid, "
            f"{self._stats.symlinks_broken} broken), "
            f"{self._stats.tracks_updated} tracks updated, "
            f"{self._stats.playlist_tracks_updated} playlist-track "
            f"relationships updated"
        )

        if self._stats.errors:
            logger.warning("%d errors during scan", len(self._stats.errors))

    def get_scan_statistics(self) -> Dict[str, Any]:
        """Get current scan statistics.

        Returns:
            Dictionary with scan statistics
        """
        return self._stats.to_dict()
