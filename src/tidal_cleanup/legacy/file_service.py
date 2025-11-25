"""File operations service for audio file management and conversion."""

import logging
import subprocess  # noqa: S404
from pathlib import Path
from typing import Dict, List, Optional, Set

from mutagen import File as MutagenFile
from mutagen.mp3 import HeaderNotFoundError

from ..models.models import ConversionJob, FileInfo, Track
from .directory_diff import DirectoryDiffService, FileIdentity

logger = logging.getLogger(__name__)


class FileOperationError(Exception):
    """Custom exception for file operation errors."""

    pass


class FileService:
    """Service for audio file operations."""

    def __init__(self, supported_extensions: Optional[tuple[str, ...]] = None) -> None:
        """Initialize file service.

        Args:
            supported_extensions: Tuple of supported file extensions
        """
        self.supported_extensions = supported_extensions or (
            ".mp3",
            ".flac",
            ".wav",
            ".aac",
            ".m4a",
            ".mp4",
        )
        self.diff_service = DirectoryDiffService()

    # @convert convert_audio_with_playlist_logic
    def _validate_audio_paths(self, source_path: Path, target_path: Path) -> None:
        """Validate audio file paths for security.

        Args:
            source_path: Source audio file path
            target_path: Target audio file path

        Raises:
            FileOperationError: If paths are invalid or potentially unsafe
        """
        # Ensure paths are absolute and resolved
        source_path = source_path.resolve()
        target_path = target_path.resolve()

        # Check that source file exists
        if not source_path.exists():
            raise FileOperationError(f"Source file does not exist: {source_path}")

        # Check that source file has a valid audio extension
        valid_source_exts = (".m4a", ".mp4", ".flac", ".wav", ".aac", ".mp3")
        if source_path.suffix.lower() not in valid_source_exts:
            raise FileOperationError(
                f"Invalid source file extension: {source_path.suffix}"
            )

        # Check that target has a valid audio extension
        valid_target_exts = (".mp3", ".flac", ".wav", ".aac")
        if target_path.suffix.lower() not in valid_target_exts:
            raise FileOperationError(
                f"Invalid target file extension: {target_path.suffix}"
            )

        # Ensure paths don't contain suspicious patterns
        # Note: We only check for backticks and pipe characters that could
        # cause command injection. Ampersands (&), semicolons (;), and dollar
        # signs ($) are common in music filenames and safe when paths are
        # properly quoted in subprocess calls.
        for path in [source_path, target_path]:
            path_str = str(path)
            if any(char in path_str for char in ["`", "|"]):
                raise FileOperationError(f"Path contains suspicious characters: {path}")

    # @convert convert_audio_with_playlist_logic
    def _validate_quality_parameter(self, quality: str) -> None:
        """Validate ffmpeg quality parameter.

        Args:
            quality: Quality parameter (should be 0-9)

        Raises:
            FileOperationError: If quality parameter is invalid
        """
        try:
            quality_int = int(quality)
            if not 0 <= quality_int <= 9:
                raise FileOperationError(f"Quality must be 0-9, got: {quality}")
        except ValueError:
            raise FileOperationError(f"Quality must be numeric, got: {quality}")

    def scan_directory(self, directory: Path) -> List[FileInfo]:
        """Scan directory for audio files.

        Args:
            directory: Directory to scan

        Returns:
            List of FileInfo objects

        Raises:
            FileOperationError: If directory doesn't exist or scan fails
        """
        if not directory.exists():
            raise FileOperationError(f"Directory does not exist: {directory}")

        if not directory.is_dir():
            raise FileOperationError(f"Path is not a directory: {directory}")

        try:
            audio_files = []
            for file_path in directory.rglob("*"):
                if file_path.suffix.lower() in self.supported_extensions:
                    try:
                        file_info = self._create_file_info(file_path)
                        audio_files.append(file_info)
                    except Exception as e:
                        logger.warning("Failed to process %s: %s", file_path, e)
                        continue

            logger.info("Found %d audio files in %s", len(audio_files), directory)
            return audio_files

        except Exception as e:
            logger.error("Failed to scan directory %s: %s", directory, e)
            raise FileOperationError(f"Cannot scan directory: {e}")

    def _create_file_info(self, file_path: Path) -> FileInfo:
        """Create FileInfo object from file path.

        Args:
            file_path: Path to audio file

        Returns:
            FileInfo object
        """
        try:
            stat = file_path.stat()

            # Try to get audio metadata
            metadata = None
            duration = None
            bitrate = None
            sample_rate = None

            try:
                audio_file = MutagenFile(file_path, easy=True)
                if audio_file is not None:
                    metadata = dict(audio_file)
                    # Get technical info if available
                    if hasattr(audio_file, "info"):
                        duration = getattr(audio_file.info, "length", None)
                        bitrate = getattr(audio_file.info, "bitrate", None)
                        sample_rate = getattr(audio_file.info, "sample_rate", None)
            except (HeaderNotFoundError, Exception) as e:
                logger.warning("Cannot read metadata for %s: %s", file_path, e)

            return FileInfo(
                path=file_path,
                name=file_path.name,
                size=stat.st_size,
                format=file_path.suffix.lower(),
                duration=int(duration) if duration else None,
                bitrate=int(bitrate) if bitrate else None,
                sample_rate=int(sample_rate) if sample_rate else None,
                metadata=metadata,
            )

        except Exception as e:
            logger.error("Failed to create FileInfo for %s: %s", file_path, e)
            raise FileOperationError(f"Cannot create FileInfo: {e}")

    def get_track_names(self, directory: Path) -> Set[str]:
        """Get set of normalized track names from directory.

        Args:
            directory: Directory to scan

        Returns:
            Set of normalized track names (lowercase file stems)
        """
        try:
            file_infos = self.scan_directory(directory)
            return {info.stem.lower() for info in file_infos}
        except Exception as e:
            logger.error("Failed to get track names from %s: %s", directory, e)
            return set()

    def get_tracks_with_metadata(self, directory: Path) -> List[Track]:
        """Get Track objects with metadata from directory.

        Args:
            directory: Directory to scan

        Returns:
            List of Track objects with metadata
        """
        tracks = []
        try:
            file_infos = self.scan_directory(directory)
            for file_info in file_infos:
                track = self.create_track_from_file(file_info)
                if track:
                    tracks.append(track)
                else:
                    # Create a basic track from filename if no metadata available
                    # Parse filename like "artist - title.ext"
                    stem = file_info.stem
                    if " - " in stem:
                        parts = stem.split(" - ", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    else:
                        artist = "Unknown Artist"
                        title = stem

                    track = Track(
                        title=title,
                        artist=artist,
                        album=None,
                        year=None,
                        duration=file_info.duration,
                        file_path=file_info.path,
                        file_size=file_info.size,
                        file_format=file_info.format,
                    )
                    tracks.append(track)

            return tracks
        except Exception as e:
            logger.error("Failed to get tracks with metadata from %s: %s", directory, e)
            return []

    def _build_ffmpeg_command(
        self, source_path: Path, target_path: Path, quality: str
    ) -> list[str]:
        """Build FFmpeg conversion command.

        Args:
            source_path: Source audio file
            target_path: Target audio file
            quality: Audio quality setting

        Returns:
            List of command arguments for FFmpeg
        """
        return [
            "ffmpeg",
            "-nostdin",
            "-i",
            str(source_path),
            "-q:a",
            quality,
            str(target_path),
        ]

    def _run_ffmpeg_conversion(
        self, source_path: Path, target_path: Path, quality: str
    ) -> None:
        """Execute FFmpeg conversion subprocess.

        Args:
            source_path: Source audio file
            target_path: Target audio file
            quality: Audio quality setting

        Raises:
            subprocess.CalledProcessError: If FFmpeg conversion fails
        """
        cmd = self._build_ffmpeg_command(source_path, target_path, quality)

        subprocess.run(  # noqa: S603
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def _handle_empty_source_file(
        self, source_path: Path, job: ConversionJob
    ) -> ConversionJob:
        """Handle conversion of empty source file.

        Args:
            source_path: Source audio file
            job: ConversionJob to update

        Returns:
            Updated ConversionJob with skipped status
        """
        logger.warning("Skipping conversion of empty file: %s", source_path)
        job.status = "completed"
        job.was_skipped = True
        return job

    def _handle_successful_conversion(
        self, source_path: Path, target_path: Path, job: ConversionJob
    ) -> ConversionJob:
        """Handle post-conversion success operations.

        Args:
            source_path: Source audio file
            target_path: Target audio file
            job: ConversionJob to update

        Returns:
            Updated ConversionJob with completed status
        """
        if target_path.exists():
            logger.info("Successfully converted: %s", source_path)
            job.status = "completed"
            self._replace_with_empty_file(source_path)
        else:
            job.status = "failed"
            job.error_message = "Target file was not created"
        return job

    def _handle_conversion_error(
        self, error: Exception, job: ConversionJob
    ) -> ConversionJob:
        """Handle conversion errors and update job status.

        Args:
            error: Exception that occurred during conversion
            job: ConversionJob to update

        Returns:
            Updated ConversionJob with failed status
        """
        if isinstance(error, subprocess.CalledProcessError):
            logger.error("ffmpeg conversion failed: %s", error.stderr)
            job.error_message = f"ffmpeg error: {error.stderr}"
        else:
            logger.error("Conversion failed: %s", error)
            job.error_message = str(error)

        job.status = "failed"
        return job

    # @convert convert_directory
    def convert_audio(
        self, source_path: Path, target_path: Path, quality: str = "2"
    ) -> ConversionJob:
        """Convert audio file with playlist-specific logic.

        This method implements the behavior where:
        1. Run ffmpeg conversion if target doesn't exist
        2. Only replace source with empty file if conversion was successful

        Args:
            source_path: Source audio file
            target_path: Target audio file
            quality: Audio quality setting

        Returns:
            ConversionJob object with conversion status
        """
        # Validate inputs for security
        self._validate_audio_paths(source_path, target_path)
        self._validate_quality_parameter(quality)

        job = ConversionJob(
            source_path=source_path,
            target_path=target_path,
            source_format=source_path.suffix.lower(),
            target_format=target_path.suffix.lower(),
            quality=quality,
        )

        # Check if source file is empty
        if source_path.stat().st_size == 0:
            return self._handle_empty_source_file(source_path, job)

        # Create target directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info("Converting %s -> %s", source_path, target_path)
            job.status = "processing"

            # Run ffmpeg conversion
            self._run_ffmpeg_conversion(source_path, target_path, quality)

            # Handle successful conversion
            return self._handle_successful_conversion(source_path, target_path, job)

        except Exception as e:
            return self._handle_conversion_error(e, job)

    def _replace_with_empty_file(self, file_path: Path) -> None:
        """Replace file with empty file (preserving original behavior).

        Args:
            file_path: File to replace with empty file
        """
        try:
            file_path.unlink()
            file_path.touch()
            logger.debug("Replaced %s with empty file", file_path)
        except Exception as e:
            logger.warning("Failed to replace file with empty: %s", e)

    def _find_playlist_directories(self, source_dir: Path) -> List[Path]:
        """Find all playlist directories under source directory.

        Args:
            source_dir: Source directory to search

        Returns:
            List of playlist directory paths
        """
        playlists_dir = source_dir / "Playlists"

        if not playlists_dir.exists():
            logger.warning(
                f"No 'Playlists' directory found in {source_dir}, "
                f"falling back to direct directory scanning"
            )
            playlists_dir = source_dir

        playlist_dirs = [d for d in playlists_dir.iterdir() if d.is_dir()]

        if not playlist_dirs:
            logger.warning("No playlist directories found in %s", playlists_dir)

        return playlist_dirs

    def _filter_playlist_by_name(
        self, playlist_dirs: List[Path], target_name: str
    ) -> List[Path]:
        """Filter playlists to find closest match to target name.

        Uses fuzzy string matching to find the best match.

        Args:
            playlist_dirs: List of playlist directory paths
            target_name: Target playlist name to match

        Returns:
            List containing the best matching playlist, or empty list if no match
        """
        from thefuzz import fuzz

        if not playlist_dirs:
            return []

        # Try exact match first (case-insensitive)
        target_lower = target_name.lower()
        for playlist_dir in playlist_dirs:
            if playlist_dir.name.lower() == target_lower:
                logger.info("Found exact match for playlist: %s", playlist_dir.name)
                return [playlist_dir]

        # Use fuzzy matching to find best match
        # Calculate similarity scores for all playlists
        scored_playlists = [
            (
                playlist_dir,
                max(
                    fuzz.ratio(target_name.lower(), playlist_dir.name.lower()),
                    fuzz.partial_ratio(target_name.lower(), playlist_dir.name.lower()),
                    fuzz.token_sort_ratio(
                        target_name.lower(), playlist_dir.name.lower()
                    ),
                ),
            )
            for playlist_dir in playlist_dirs
        ]

        # Sort by score (highest first)
        scored_playlists.sort(key=lambda x: x[1], reverse=True)

        # Get the best match
        best_match, best_score = scored_playlists[0]

        # Only return if score is above threshold (60% similarity)
        if best_score >= 60:
            logger.info(
                f"Found fuzzy match for '{target_name}': "
                f"{best_match.name} (score: {best_score})"
            )
            return [best_match]

        logger.warning(
            f"No playlist found matching '{target_name}' "
            f"(best match: {best_match.name} with score {best_score})"
        )
        return []

    def _convert_missing_files(
        self,
        source_dir: Path,
        target_dir: Path,
        file_stems: Set[str],
        source_identities: Dict[str, FileIdentity],
        target_format: str,
        quality: str,
    ) -> List[ConversionJob]:
        """Convert files that exist only in source directory.

        Args:
            source_dir: Source playlist directory
            target_dir: Target playlist directory
            file_stems: Set of file stems to convert
            source_identities: Dictionary mapping stems to source file identities
            target_format: Target file format
            quality: Audio quality setting

        Returns:
            List of ConversionJob objects
        """
        jobs = []

        for file_stem in file_stems:
            source_file_identity = source_identities[file_stem]
            source_file = source_file_identity.path.resolve()

            # Calculate target path
            relative_to_playlist = source_file.relative_to(source_dir.resolve())
            target_file = (target_dir / relative_to_playlist).with_suffix(target_format)

            # Convert file
            job = self.convert_audio(source_file, target_file, quality)
            jobs.append(job)

        return jobs

    def _delete_orphaned_files(
        self,
        file_stems: Set[str],
        target_identities: Dict[str, FileIdentity],
        target_format: str,
        quality: str,
    ) -> List[ConversionJob]:
        """Delete files that exist only in target directory.

        Args:
            file_stems: Set of file stems to delete
            target_identities: Dictionary mapping stems to target file identities
            target_format: Target file format
            quality: Audio quality setting

        Returns:
            List of ConversionJob objects representing deletions
        """
        jobs = []

        for file_stem in file_stems:
            target_file_identity = target_identities[file_stem]
            target_file = target_file_identity.path

            try:
                target_file.unlink()
                logger.info("Deleted orphaned target file: %s", target_file)

                # Track as a special job type
                job = ConversionJob(
                    source_path=Path(""),  # No source for deletion
                    target_path=target_file,
                    source_format="",
                    target_format=target_format,
                    quality=quality,
                    status="deleted",
                    was_skipped=False,
                )
                jobs.append(job)
            except OSError as e:
                logger.error("Failed to delete %s: %s", target_file, e)

        return jobs

    def _track_skipped_files(
        self,
        file_stems: Set[str],
        source_identities: Dict[str, FileIdentity],
        target_identities: Dict[str, FileIdentity],
        target_format: str,
        quality: str,
    ) -> List[ConversionJob]:
        """Track files that already exist in both directories.

        Args:
            file_stems: Set of file stems that exist in both directories
            source_identities: Dictionary mapping stems to source file identities
            target_identities: Dictionary mapping stems to target file identities
            target_format: Target file format
            quality: Audio quality setting

        Returns:
            List of ConversionJob objects with was_skipped=True
        """
        jobs = []

        for file_stem in file_stems:
            source_file_identity = source_identities[file_stem]
            target_file_identity = target_identities[file_stem]

            job = ConversionJob(
                source_path=source_file_identity.path,
                target_path=target_file_identity.path,
                source_format=source_file_identity.path.suffix.lower(),
                target_format=target_format,
                quality=quality,
                status="completed",
                was_skipped=True,
            )
            jobs.append(job)

        return jobs

    def _process_single_playlist(
        self,
        playlist_dir: Path,
        source_dir: Path,
        target_dir: Path,
        target_format: str,
        quality: str,
    ) -> List[ConversionJob]:
        """Process a single playlist directory.

        Args:
            playlist_dir: Playlist directory to process
            source_dir: Root source directory
            target_dir: Root target directory
            target_format: Target file format
            quality: Audio quality setting

        Returns:
            List of ConversionJob objects for this playlist
        """
        playlist_name = playlist_dir.name

        # Calculate corresponding target directory
        relative_path = playlist_dir.relative_to(source_dir)
        target_playlist_dir = target_dir / relative_path

        logger.debug("Processing playlist: %s", playlist_name)

        # Use diff service to compare directories
        diff = self.diff_service.compare_by_stem_with_extension_mapping(
            source_dir=playlist_dir,
            target_dir=target_playlist_dir,
            source_extensions=(".m4a", ".mp4"),
            target_extensions=(target_format,),
        )

        # Process all three categories of files
        jobs = []

        # Convert missing files
        jobs.extend(
            self._convert_missing_files(
                playlist_dir,
                target_playlist_dir,
                diff.only_in_source,
                diff.source_identities,
                target_format,
                quality,
            )
        )

        # Delete orphaned files
        jobs.extend(
            self._delete_orphaned_files(
                diff.only_in_target,
                diff.target_identities,
                target_format,
                quality,
            )
        )

        # Track skipped files
        jobs.extend(
            self._track_skipped_files(
                diff.in_both,
                diff.source_identities,
                diff.target_identities,
                target_format,
                quality,
            )
        )

        return jobs

    # @convert _convert_files()
    def convert_directory(
        self,
        source_dir: Path,
        target_dir: Path,
        target_format: str = ".mp3",
        quality: str = "2",
        playlist_filter: Optional[str] = None,
    ) -> dict[str, List[ConversionJob]]:
        """Convert all audio files with playlist-based reporting.

        Uses directory diff mechanism to only process files that differ:
        - Converts files that exist in source but not in target
        - Deletes files that exist in target but not in source
        - Skips files that already exist in both

        Args:
            source_dir: Source directory
            target_dir: Target directory
            target_format: Target file format (e.g., ".mp3")
            quality: Audio quality setting
            playlist_filter: Optional playlist name to filter. If provided,
                           only the closest matching playlist will be converted.

        Returns:
            Dictionary mapping playlist names to lists of ConversionJob objects
        """
        logger.info(
            f"Converting files from {source_dir} to {target_dir} "
            f"using diff-based optimization"
        )

        playlist_jobs: dict[str, List[ConversionJob]] = {}

        # Find all playlist directories
        playlist_dirs = self._find_playlist_directories(source_dir)
        if not playlist_dirs:
            return playlist_jobs

        # Filter to single playlist if requested
        if playlist_filter:
            playlist_dirs = self._filter_playlist_by_name(
                playlist_dirs, playlist_filter
            )
            if not playlist_dirs:
                logger.warning("No playlist found matching '%s'", playlist_filter)
                return playlist_jobs

        # Process each playlist directory
        for playlist_dir in playlist_dirs:
            playlist_name = playlist_dir.name

            jobs = self._process_single_playlist(
                playlist_dir, source_dir, target_dir, target_format, quality
            )

            playlist_jobs[playlist_name] = jobs

        return playlist_jobs

    def delete_file(self, file_path: Path, interactive: bool = True) -> bool:
        """Delete a file with optional confirmation.

        Args:
            file_path: File to delete
            interactive: Whether to ask for confirmation

        Returns:
            True if file was deleted, False otherwise
        """
        if not file_path.exists():
            logger.warning("File does not exist: %s", file_path)
            return False

        if interactive:
            confirm = input(f"Delete {file_path}? [y/N]: ").strip().lower()
            if confirm not in ["y", "yes"]:
                logger.info("Deletion cancelled by user")
                return False

        try:
            file_path.unlink()
            logger.info("Deleted: %s", file_path)
            return True
        except Exception as e:
            logger.error("Failed to delete %s: %s", file_path, e)
            return False

    def create_track_from_file(self, file_info: FileInfo) -> Optional[Track]:
        """Create Track object from FileInfo.

        Args:
            file_info: FileInfo object

        Returns:
            Track object if metadata is available, None otherwise
        """
        if not file_info.metadata:
            return None

        try:
            metadata = file_info.metadata

            return Track(
                title=metadata.get("title", [file_info.stem])[0],
                artist=metadata.get("artist", ["Unknown Artist"])[0],
                album=metadata.get("album", [None])[0],
                genre=metadata.get("genre", [None])[0],
                duration=file_info.duration,
                file_path=file_info.path,
                file_size=file_info.size,
                file_format=file_info.format,
            )

        except Exception as e:
            logger.warning("Failed to create Track from %s: %s", file_info.path, e)
            return None
