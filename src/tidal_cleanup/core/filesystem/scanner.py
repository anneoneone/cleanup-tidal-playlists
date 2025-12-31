"""Filesystem scanner for unified Tidal-Filesystem sync.

This service scans the mp3/Playlists/* directories to identify what files
currently exist on the filesystem, and updates the database
with the current filesystem state. It's the second step in the unified sync
workflow: Tidal fetch → Filesystem scan → Compare → Sync.
"""

import logging
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...database.models import DownloadStatus, PlaylistSource, PlaylistSyncStatus
from ...database.service import DatabaseService

logger = logging.getLogger(__name__)


@dataclass
class ScanStatistics:
    """Statistics from filesystem scan operation."""

    playlists_scanned: int = 0
    files_found: int = 0
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
        # Library root is typically the parent of the playlists directory (mp3 folder)
        self.library_root = self.playlists_root.parent
        self.supported_extensions = supported_extensions
        self._stats = ScanStatistics()

    def scan_playlist(self, playlist_name: str) -> Dict[str, Any]:
        """Scan a single playlist directory and update database.

        Args:
            playlist_name: Name of the playlist to scan

        Returns:
            Dictionary with scan statistics

        Raises:
            RuntimeError: If playlists root directory doesn't exist
            ValueError: If playlist directory doesn't exist
        """
        playlist_dir = self.playlists_root / playlist_name

        if not playlist_dir.exists() or not playlist_dir.is_dir():
            raise ValueError(f"Playlist directory does not exist: {playlist_dir}")

        logger.info("Scanning playlist: %s", playlist_name)
        return self._scan_playlists([playlist_dir])

    def scan_all_playlists(self) -> Dict[str, Any]:
        """Scan all playlist directories and update database.

        Returns:
            Dictionary with scan statistics

        Raises:
            RuntimeError: If playlists root directory doesn't exist
        """
        logger.info("Scanning playlists from: %s", self.playlists_root)

        # Get all playlist directories
        playlist_dirs = self._find_playlist_directories()
        logger.info("Found %d playlist directories", len(playlist_dirs))

        return self._scan_playlists(playlist_dirs)

    def _scan_playlists(self, playlist_dirs: List[Path]) -> Dict[str, Any]:
        """Internal method to scan a list of playlist directories.

        Args:
            playlist_dirs: List of playlist directory paths to scan

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
        if not self.playlists_root.exists():
            raise RuntimeError(
                f"Playlists root directory does not exist: {self.playlists_root}"
            )

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

            # Determine if this is a local-only directory or matched to Tidal
            if playlist and playlist.source == "tidal":
                # Use existing Tidal playlist (files will match via track metadata)
                logger.debug(f"Using existing Tidal playlist: '{playlist_name}'")
            elif not playlist:
                # Create local-only playlist for directories not in database
                logger.info(
                    f"Creating local-only playlist for directory: '{playlist_name}'"
                )
                playlist = self._create_local_playlist(playlist_name, playlist_dir)
                if not playlist:
                    logger.warning(
                        f"Failed to create playlist for '{playlist_name}', skipping"
                    )
                    self._stats.playlists_scanned += 1
                    return
            # else: use existing playlist (already local or other source)

            # Preload playlist-track associations to prefer playlist-specific tracks
            playlist_tracks = self.db_service.get_playlist_track_associations(
                playlist.id
            )
            normalized_playlist_tracks: Dict[str, List[Any]] = {}
            for playlist_track in playlist_tracks:
                track = playlist_track.track
                if not track or not track.normalized_name:
                    continue
                normalized_playlist_tracks.setdefault(track.normalized_name, []).append(
                    track
                )

            # Find all audio files in playlist directory
            files = self._find_audio_files(playlist_dir)
            logger.debug("Found %d files in %s", len(files), playlist_name)

            # Track if this is a local-only playlist for post-processing
            is_local_only = (
                playlist.source == "local" if hasattr(playlist, "source") else False
            )

            # Process each file
            for file_path in files:
                self._process_file(
                    playlist, file_path, normalized_playlist_tracks, is_local_only
                )

            self._stats.playlists_scanned += 1

        except Exception as e:
            error_msg = (
                f"Error processing playlist directory '{playlist_dir.name}': {e}"
            )
            logger.error(error_msg)
            self._stats.errors.append(error_msg)

    def _create_local_playlist(self, playlist_name: str, playlist_dir: Path) -> Any:
        """Create a local-only playlist entry in the database.

        Args:
            playlist_name: Name of the local playlist (directory name)
            playlist_dir: Path to the playlist directory

        Returns:
            Playlist object if created, else None
        """
        try:
            playlist_data = {
                "name": playlist_name,
                "tidal_id": None,
                "source": PlaylistSource.LOCAL.value,
                "local_folder_path": str(playlist_dir.relative_to(self.library_root)),
                "sync_status": PlaylistSyncStatus.UNKNOWN.value,
                "last_synced_filesystem": datetime.now(timezone.utc),
            }
            playlist = self.db_service.create_playlist(playlist_data)
            logger.debug("Created local-only playlist: %s", playlist_name)
            return playlist
        except Exception:
            logger.exception("Failed to create local-only playlist: %s", playlist_name)
            return None

    def _find_audio_files(self, directory: Path) -> List[Path]:
        """Find all audio files in directory (non-recursive).

        Args:
            directory: Directory to search

        Returns:
            List of audio file paths
        """
        audio_files: List[Path] = []

        for item in directory.iterdir():
            if item.is_file() and item.suffix.lower() in self.supported_extensions:
                audio_files.append(item)

        return sorted(audio_files)

    def _process_file(
        self,
        playlist: Any,
        file_path: Path,
        playlist_tracks_map: Dict[str, List[Any]],
        is_local_only: bool = False,
    ) -> None:
        """Process a single file.

        Args:
            playlist: Playlist database object
            file_path: Path to file
            playlist_tracks_map: Lookup of playlist tracks keyed by normalized name
            is_local_only: Whether this is a local-only playlist
        """
        try:
            self._stats.files_found += 1

            relative_path = self._to_library_relative_path(file_path)

            # Try to match file to a track
            track, normalized_key = self._match_file_to_track(
                file_path, playlist_tracks_map, relative_path
            )

            if track:
                if self._update_track_file_metadata(track.id, file_path):
                    self._stats.tracks_updated += 1

                # For all playlists: mark track as present locally
                self._ensure_local_playlist_track(playlist, track)

                # Add this file path to all playlist tracks that reference it
                self._update_file_paths_for_targets(
                    normalized_key, playlist_tracks_map, track, relative_path
                )
            elif is_local_only:
                # Only create new tracks for local-only playlists
                new_track = self._create_track_from_file(file_path, relative_path)
                if new_track:
                    self._ensure_local_playlist_track(playlist, new_track)

        except Exception as e:
            error_msg = f"Error processing file '{file_path.name}': {e}"
            logger.error(error_msg)
            self._stats.errors.append(error_msg)

    def _match_file_to_track(
        self,
        file_path: Path,
        playlist_tracks_map: Optional[Dict[str, List[Any]]] = None,
        relative_path: Optional[str] = None,
    ) -> tuple[Any | None, Optional[str]]:
        """Match a file to a database track.

        Uses filename-based matching for now. Future: metadata, ISRC, etc.

        Args:
            file_path: Path to file
            playlist_tracks_map: Optional lookup of playlist tracks by normalized name
            relative_path: Relative library path for tie-breaking

        Returns:
            Tuple of (Track or None, normalized_name used for lookup)
        """
        filename = file_path.stem

        artist_title = self._split_artist_title(filename)
        if artist_title:
            artist, title = artist_title
            match = self._match_by_artist_title(
                artist, title, playlist_tracks_map, relative_path
            )
            if match:
                return match

        fallback_match = self._match_by_filename_keyword(filename)
        if fallback_match:
            return fallback_match

        logger.debug("Could not match file to track: %s", file_path.name)
        return None, None

    def _split_artist_title(self, filename: str) -> Optional[tuple[str, str]]:
        """Split "Artist - Title" filenames when possible."""
        if " - " not in filename:
            return None
        parts = filename.split(" - ", 1)
        if len(parts) != 2:
            return None
        return parts[0], parts[1]

    def _match_by_artist_title(
        self,
        artist: str,
        title: str,
        playlist_tracks_map: Optional[Dict[str, List[Any]]],
        relative_path: Optional[str],
    ) -> Optional[tuple[Any, str]]:
        """Use normalized name matching based on artist/title."""
        title_clean = title.strip()

        for artist_variant in self._generate_artist_variations(artist):
            artist_clean = artist_variant.strip()
            # Try the same normalization used when importing from Tidal first,
            # then fall back to the stricter DatabaseService normalization so
            # we can match existing rows regardless of how they were written.
            normalized_candidates = [
                f"{artist_clean.lower()} - {title_clean.lower()}",
            ]

            alt_normalized = DatabaseService._normalize_track_name(
                title_clean, artist_clean
            )
            if alt_normalized not in normalized_candidates:
                normalized_candidates.append(alt_normalized)

            for normalized_name in normalized_candidates:
                candidate = self._match_in_playlist_map(
                    normalized_name, playlist_tracks_map, relative_path
                )
                if candidate:
                    return candidate, normalized_name

                track = self.db_service.find_track_by_normalized_name(normalized_name)
                if track:
                    return track, normalized_name
        return None

    def _match_in_playlist_map(
        self,
        normalized_name: str,
        playlist_tracks_map: Optional[Dict[str, List[Any]]],
        relative_path: Optional[str],
    ) -> Optional[Any]:
        """Return a playlist-specific match if available."""
        if not playlist_tracks_map:
            return None
        playlist_candidates = playlist_tracks_map.get(normalized_name)
        if not playlist_candidates:
            return None
        if relative_path:
            for candidate in playlist_candidates:
                if not candidate.file_paths or (
                    relative_path not in candidate.file_paths
                ):
                    return candidate
        return playlist_candidates[0]

    def _match_by_filename_keyword(
        self, filename: str
    ) -> Optional[tuple[Any, Optional[str]]]:
        """Fallback matching by checking filename as substring."""
        filename_lower = filename.lower()
        for track in self.db_service.get_all_tracks():
            if track.normalized_name and filename_lower in track.normalized_name:
                return track, track.normalized_name
        return None

    def _update_file_paths_for_targets(
        self,
        normalized_key: Optional[str],
        playlist_tracks_map: Dict[str, List[Any]],
        track: Any,
        relative_path: str,
    ) -> None:
        """Update file path for candidates referencing the track."""
        targets: List[Any]
        if normalized_key and playlist_tracks_map:
            targets = playlist_tracks_map.get(normalized_key, []) or [track]
        else:
            targets = [track]

        for candidate in targets:
            try:
                self.db_service.add_file_path_to_track(candidate.id, relative_path)
            except ValueError:
                logger.debug(
                    "Skipping empty path assignment for track %s", candidate.id
                )

    def _ensure_local_playlist_track(self, playlist: Any, track: Any) -> None:
        """Ensure the playlist-track association marks local presence."""
        try:
            logger.debug(
                "Adding track %s to playlist %s (ID: %s) as local",
                getattr(track, "id", "?"),
                getattr(playlist, "name", "?"),
                getattr(playlist, "id", "?"),
            )
            result = self.db_service.add_track_to_playlist(
                playlist.id, track.id, in_local=True
            )
            logger.debug(
                "Successfully added, result ID: %s", getattr(result, "id", "?")
            )
            self._stats.playlist_tracks_updated += 1
        except Exception as exc:
            logger.error(
                "Failed to add track %s to playlist %s: %s",
                getattr(track, "id", "?"),
                getattr(playlist, "id", "?"),
                exc,
                exc_info=True,
            )

    def _create_track_from_file(
        self, file_path: Path, relative_path: str
    ) -> Optional[Any]:
        """Create a new Track from the filesystem file and return it."""
        artist = "Unknown"
        title = file_path.stem
        split = self._split_artist_title(file_path.stem)
        if split:
            artist, title = split

        file_stat = None
        with suppress(OSError):
            file_stat = file_path.stat()

        track_data: Dict[str, Any] = {
            "title": title,
            "artist": artist,
            "file_paths": [relative_path],
            "download_status": DownloadStatus.DOWNLOADED.value,
        }
        if file_stat:
            track_data.update(
                {
                    "file_size_bytes": file_stat.st_size,
                    "file_last_modified": datetime.fromtimestamp(file_stat.st_mtime),
                }
            )

        try:
            new_track = self.db_service.create_track(track_data)
            self._stats.tracks_updated += 1
            logger.debug(
                "Created new local track '%s - %s'",
                artist,
                title,
            )
            return new_track
        except Exception as exc:
            logger.exception(
                "Failed creating track for file %s: %s",
                file_path,
                exc,
            )
            return None

    def _generate_artist_variations(self, artist_field: str) -> List[str]:
        """Generate possible artist tokens from a filename artist field."""
        candidates: List[str] = []
        normalized = artist_field.strip()
        if normalized:
            candidates.append(normalized)

        simple_separators = [",", "&", "+", "/", "|"]
        token_separators = [" x ", " vs ", " feat", " ft", " featuring", " pres"]

        for sep in simple_separators:
            if sep in normalized:
                candidates.append(normalized.split(sep, 1)[0].strip())

        lower_artist = normalized.lower()
        for token in token_separators:
            idx = lower_artist.find(token)
            if idx > 0:
                candidates.append(normalized[:idx].strip())

        # Deduplicate while preserving order
        seen = set()
        unique_candidates: List[str] = []
        for entry in candidates:
            if entry and entry.lower() not in seen:
                unique_candidates.append(entry)
                seen.add(entry.lower())

        return unique_candidates

    def _update_track_file_metadata(self, track_id: int, file_path: Path) -> bool:
        """Persist filesystem metadata for a track based on a resolved path."""
        try:
            file_stat = file_path.stat()
        except OSError as exc:
            logger.warning(
                "Cannot update track %s metadata, file unavailable: %s",
                track_id,
                exc,
            )
            return False

        update_data = {
            "file_size_bytes": file_stat.st_size,
            "file_last_modified": datetime.fromtimestamp(file_stat.st_mtime),
            "download_status": DownloadStatus.DOWNLOADED.value,
        }

        try:
            self.db_service.update_track(track_id, update_data)
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to update track %s metadata for %s: %s",
                track_id,
                file_path,
                exc,
            )
            return False

    def _to_library_relative_path(self, file_path: Path) -> str:
        """Return a path relative to the MP3 library root when possible."""
        try:
            return str(file_path.relative_to(self.library_root))
        except ValueError:
            return str(file_path)

    def _log_scan_summary(self) -> None:
        """Log summary of scan operation."""
        logger.info(
            f"Filesystem scan complete: "
            f"{self._stats.playlists_scanned} playlists scanned, "
            f"{self._stats.files_found} files found, "
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
