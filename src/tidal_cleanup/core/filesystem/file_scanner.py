"""Local File Scanner Service for matching files to database tracks."""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mutagen

from ...database.models import Track
from ...database.service import DatabaseService

# Alias for mutagen.File - mutagen doesn't have type stubs
MutagenFile = mutagen.File

logger = logging.getLogger(__name__)


class FileScannerService:
    """Service for scanning local files and matching to database tracks."""

    def __init__(
        self,
        db_service: DatabaseService,
        supported_extensions: Optional[Tuple[str, ...]] = None,
    ):
        """Initialize file scanner service.

        Args:
            db_service: DatabaseService instance for database operations
            supported_extensions: Tuple of supported file extensions
        """
        self.db_service = db_service
        self.supported_extensions = supported_extensions or (
            ".mp3",
            ".flac",
            ".wav",
            ".aac",
            ".m4a",
            ".mp4",
        )

    def scan_directory(self, directory: Path, update_db: bool = True) -> Dict[str, Any]:
        """Scan directory for audio files and match to database tracks.

        Args:
            directory: Directory to scan
            update_db: Whether to update database with findings

        Returns:
            Dictionary with scan results including matched, unmatched,
            and orphaned files
        """
        logger.info("Scanning directory: %s", directory)

        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        # Find all audio files
        audio_files = self._find_audio_files(directory)
        logger.info("Found %d audio files", len(audio_files))

        # Get all tracks from database
        db_tracks = self.db_service.get_all_tracks()
        logger.info("Found %d tracks in database", len(db_tracks))

        # Match files to tracks
        matched = []
        unmatched_files = []
        file_to_track_map = {}

        for file_path in audio_files:
            track = self._match_file_to_track(file_path, db_tracks)
            if track:
                matched.append((file_path, track))
                file_to_track_map[str(file_path)] = track.id
                if update_db:
                    self._update_track_file_info(track, file_path)
            else:
                unmatched_files.append(file_path)

        # Find orphaned tracks (in database but no file found)
        matched_track_ids = {track.id for _, track in matched}
        orphaned_tracks = [t for t in db_tracks if t.id not in matched_track_ids]

        logger.info(
            f"Scan complete: {len(matched)} matched, "
            f"{len(unmatched_files)} unmatched files, "
            f"{len(orphaned_tracks)} orphaned tracks"
        )

        return {
            "matched": matched,
            "unmatched_files": unmatched_files,
            "orphaned_tracks": orphaned_tracks,
            "total_files": len(audio_files),
            "total_tracks": len(db_tracks),
        }

    def _find_audio_files(self, directory: Path) -> List[Path]:
        """Find all audio files in directory and subdirectories.

        Args:
            directory: Directory to search

        Returns:
            List of audio file paths
        """
        audio_files: List[Path] = []
        for ext in self.supported_extensions:
            audio_files.extend(directory.rglob(f"*{ext}"))
        return sorted(audio_files)

    def _match_file_to_track(
        self, file_path: Path, db_tracks: List[Track]
    ) -> Optional[Track]:
        """Match a file to a database track.

        Uses multiple matching strategies:
        1. File path match
        2. ISRC match
        3. Metadata match (title, artist, album)
        4. File hash match (if available)

        Args:
            file_path: Path to audio file
            db_tracks: List of database tracks

        Returns:
            Matched Track or None
        """
        # Strategy 1: Match by file path
        match = self._match_by_file_path(file_path, db_tracks)
        if match:
            return match

        # Extract metadata from file
        metadata = self._extract_file_metadata(file_path)
        if not metadata:
            return None

        # Strategy 2: Match by ISRC (most reliable)
        match = self._match_by_isrc(metadata, db_tracks)
        if match:
            return match

        # Strategy 3: Match by metadata (title + artist + album)
        match = self._match_by_metadata(metadata, db_tracks)
        if match:
            return match

        # Strategy 4: Match by file hash (if stored)
        match = self._match_by_file_hash(file_path, db_tracks)
        if match:
            return match

        return None

    def _match_by_file_path(
        self, file_path: Path, db_tracks: List[Track]
    ) -> Optional[Track]:
        """Match by file path.

        Args:
            file_path: Path to audio file
            db_tracks: List of database tracks

        Returns:
            Matched Track or None
        """
        for track in db_tracks:
            if track.file_path and Path(track.file_path) == file_path:
                return track
        return None

    def _match_by_isrc(
        self, metadata: Dict[str, Any], db_tracks: List[Track]
    ) -> Optional[Track]:
        """Match by ISRC code.

        Args:
            metadata: File metadata dictionary
            db_tracks: List of database tracks

        Returns:
            Matched Track or None
        """
        isrc = metadata.get("isrc")
        if not isrc:
            return None

        for track in db_tracks:
            if track.isrc and track.isrc == isrc:
                return track
        return None

    def _match_by_metadata(
        self, metadata: Dict[str, Any], db_tracks: List[Track]
    ) -> Optional[Track]:
        """Match by metadata (title, artist, album).

        Args:
            metadata: File metadata dictionary
            db_tracks: List of database tracks

        Returns:
            Matched Track or None
        """
        title = metadata.get("title", "").lower()
        artist = metadata.get("artist", "").lower()
        album = metadata.get("album", "").lower()

        if not (title and artist):
            return None

        for track in db_tracks:
            track_title = (track.title or "").lower()
            track_artist = (track.artist or "").lower()
            track_album = (track.album or "").lower()

            # Exact match
            if (
                track_title == title
                and track_artist == artist
                and (not album or track_album == album)
            ):
                return track

            # Fuzzy match (contains)
            if (
                title in track_title
                and artist in track_artist
                and (not album or album in track_album)
            ):
                return track

        return None

    def _match_by_file_hash(
        self, file_path: Path, db_tracks: List[Track]
    ) -> Optional[Track]:
        """Match by file hash.

        Args:
            file_path: Path to audio file
            db_tracks: List of database tracks

        Returns:
            Matched Track or None
        """
        file_hash = self._compute_file_hash(file_path)
        if not file_hash:
            return None

        for track in db_tracks:
            if track.file_hash and track.file_hash == file_hash:
                return track
        return None

    def _extract_file_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Extract metadata from audio file.

        Args:
            file_path: Path to audio file

        Returns:
            Dictionary with metadata or None if extraction fails
        """
        try:
            audio = MutagenFile(file_path, easy=True)
            if not audio:
                return None

            metadata = {
                "title": self._get_tag_value(audio, "title"),
                "artist": self._get_tag_value(audio, "artist"),
                "album": self._get_tag_value(audio, "album"),
                "isrc": self._get_tag_value(audio, "isrc"),
                "duration": getattr(audio.info, "length", None),
            }

            return metadata

        except Exception as e:
            logger.warning("Failed to extract metadata from %s: %s", file_path, e)
            return None

    def _get_tag_value(self, audio: Any, tag: str) -> Optional[str]:
        """Get tag value from audio file.

        Args:
            audio: Mutagen audio object
            tag: Tag name

        Returns:
            Tag value or None
        """
        if not (hasattr(audio, "tags") and audio.tags and tag in audio.tags):
            return None

        try:
            value = audio.tags[tag]
            if isinstance(value, list) and value:
                return str(value[0])
            return str(value)
        except Exception:
            return None

    def _compute_file_hash(self, file_path: Path) -> Optional[str]:
        """Compute SHA256 hash of file.

        Args:
            file_path: Path to file

        Returns:
            Hex digest of file hash or None if computation fails
        """
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.warning("Failed to compute hash for %s: %s", file_path, e)
            return None

    def _update_track_file_info(self, track: Track, file_path: Path) -> None:
        """Update track with file information.

        Args:
            track: Track to update
            file_path: Path to file
        """
        try:
            # Compute file hash
            file_hash = self._compute_file_hash(file_path)

            # Update track
            update_data: Dict[str, Any] = {
                "file_path": str(file_path),
                "file_hash": file_hash,
            }

            self.db_service.update_track(track.id, update_data)
            logger.debug("Updated track %s with file info: %s", track.id, file_path)

        except Exception as e:
            logger.error("Failed to update track %s file info: %s", track.id, e)

    def find_missing_files(self) -> List[Track]:
        """Find tracks in database that have no corresponding local file.

        Returns:
            List of tracks with missing files
        """
        db_tracks = self.db_service.get_all_tracks()
        missing = []

        for track in db_tracks:
            if track.file_path:
                if not Path(track.file_path).exists():
                    missing.append(track)
            else:
                # No file path set at all
                missing.append(track)

        logger.info("Found %d tracks with missing files", len(missing))
        return missing

    def find_orphaned_files(self, directory: Path) -> List[Path]:
        """Find files in directory that are not in database.

        Args:
            directory: Directory to scan

        Returns:
            List of orphaned file paths
        """
        audio_files = self._find_audio_files(directory)
        db_tracks = self.db_service.get_all_tracks()

        # Create set of known file paths
        known_paths = {
            Path(track.file_path).resolve() for track in db_tracks if track.file_path
        }

        # Find files not in database
        orphaned = [f for f in audio_files if f.resolve() not in known_paths]

        logger.info("Found %d orphaned files", len(orphaned))
        return orphaned

    def update_file_hashes(self, directory: Optional[Path] = None) -> int:
        """Update file hashes for all tracks.

        Args:
            directory: Optional directory to limit scan to

        Returns:
            Number of tracks updated
        """
        if directory:
            # Get tracks with files in this directory
            db_tracks = self.db_service.get_all_tracks()
            tracks = [
                t for t in db_tracks if t.file_path and str(directory) in t.file_path
            ]
        else:
            tracks = self.db_service.get_all_tracks()

        updated = 0
        for track in tracks:
            if not track.file_path:
                continue

            file_path = Path(track.file_path)
            if not file_path.exists():
                continue

            # Compute hash
            file_hash = self._compute_file_hash(file_path)
            if file_hash and file_hash != track.file_hash:
                self.db_service.update_track(track.id, {"file_hash": file_hash})
                updated += 1

        logger.info("Updated %s file hashes", updated)
        return updated

    def verify_file_integrity(self) -> Dict[str, List[Track]]:
        """Verify integrity of all tracked files.

        Checks if files exist and if hashes match.

        Returns:
            Dictionary with lists of tracks by status:
            - valid: Files exist and hashes match
            - missing: Files don't exist
            - modified: Files exist but hashes don't match
            - no_hash: Files exist but no hash stored
        """
        db_tracks = self.db_service.get_all_tracks()

        valid = []
        missing = []
        modified = []
        no_hash = []

        for track in db_tracks:
            if not track.file_path:
                no_hash.append(track)
                continue

            file_path = Path(track.file_path)
            if not file_path.exists():
                missing.append(track)
                continue

            if not track.file_hash:
                no_hash.append(track)
                continue

            # Verify hash
            current_hash = self._compute_file_hash(file_path)
            if current_hash == track.file_hash:
                valid.append(track)
            else:
                modified.append(track)

        logger.info(
            f"File integrity check: {len(valid)} valid, "
            f"{len(missing)} missing, {len(modified)} modified, "
            f"{len(no_hash)} no hash"
        )

        return {
            "valid": valid,
            "missing": missing,
            "modified": modified,
            "no_hash": no_hash,
        }
