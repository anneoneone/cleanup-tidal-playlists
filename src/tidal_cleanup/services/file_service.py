"""File operations service for audio file management and conversion."""

import logging
import subprocess  # nosec B404
from pathlib import Path
from typing import List, Optional, Set

from mutagen import File as MutagenFile
from mutagen.mp3 import HeaderNotFoundError

from ..models.models import ConversionJob, FileInfo, Track

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
                        logger.warning(f"Failed to process {file_path}: {e}")
                        continue

            logger.info(f"Found {len(audio_files)} audio files in {directory}")
            return audio_files

        except Exception as e:
            logger.error(f"Failed to scan directory {directory}: {e}")
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
                logger.warning(f"Cannot read metadata for {file_path}: {e}")

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
            logger.error(f"Failed to create FileInfo for {file_path}: {e}")
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
            logger.error(f"Failed to get track names from {directory}: {e}")
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
            logger.error(f"Failed to get tracks with metadata from {directory}: {e}")
            return []

    def convert_audio(
        self, source_path: Path, target_path: Path, quality: str = "2"
    ) -> ConversionJob:
        """Convert audio file using ffmpeg.

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

        # Skip if target already exists
        if target_path.exists():
            logger.info(f"Target file already exists: {target_path}")
            job.status = "completed"
            return job

        # Create target directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"Converting {source_path} -> {target_path}")
            job.status = "processing"

            # Run ffmpeg conversion
            # Note: Paths are validated above for security
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-i",
                str(source_path),
                "-q:a",
                quality,
                str(target_path),
            ]

            subprocess.run(  # nosec B603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            if target_path.exists():
                logger.info(f"Successfully converted: {source_path}")
                job.status = "completed"

                # Replace source with empty file (as in original code)
                self._replace_with_empty_file(source_path)
            else:
                job.status = "failed"
                job.error_message = "Target file was not created"

        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg conversion failed: {e.stderr}")
            job.status = "failed"
            job.error_message = f"ffmpeg error: {e.stderr}"

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            job.status = "failed"
            job.error_message = str(e)

        return job

    def convert_audio_with_playlist_logic(
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

        # Create target directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"Converting {source_path} -> {target_path}")
            job.status = "processing"

            # Run ffmpeg conversion
            # Note: Paths are validated above for security
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-i",
                str(source_path),
                "-q:a",
                quality,
                str(target_path),
            ]

            subprocess.run(  # nosec B603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            # Check if conversion was successful
            if target_path.exists():
                logger.info(f"Successfully converted: {source_path}")
                job.status = "completed"

                # Only replace source with empty file if conversion was successful
                self._replace_with_empty_file(source_path)
            else:
                job.status = "failed"
                job.error_message = "Target file was not created"

        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg conversion failed: {e.stderr}")
            job.status = "failed"
            job.error_message = f"ffmpeg error: {e.stderr}"

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            job.status = "failed"
            job.error_message = str(e)

        return job

    def _replace_with_empty_file(self, file_path: Path) -> None:
        """Replace file with empty file (preserving original behavior).

        Args:
            file_path: File to replace with empty file
        """
        try:
            file_path.unlink()
            file_path.touch()
            logger.debug(f"Replaced {file_path} with empty file")
        except Exception as e:
            logger.warning(f"Failed to replace file with empty: {e}")

    def convert_directory(
        self,
        source_dir: Path,
        target_dir: Path,
        target_format: str = ".mp3",
        quality: str = "2",
    ) -> List[ConversionJob]:
        """Convert all audio files in directory to target format.

        Args:
            source_dir: Source directory
            target_dir: Target directory
            target_format: Target file format (e.g., ".mp3")
            quality: Audio quality setting

        Returns:
            List of ConversionJob objects
        """
        logger.info(f"Converting files from {source_dir} to {target_dir}")

        jobs = []
        source_files: list[Path] = []

        # Collect all source files
        for ext in [".m4a", ".mp4"]:  # As in original code
            source_files.extend(source_dir.rglob(f"*{ext}"))

        for source_file in source_files:
            # Calculate relative path and target path
            relative_path = source_file.relative_to(source_dir)
            target_file = target_dir / relative_path.with_suffix(target_format)

            # Check if file exists in both directories (playlist-based logic)
            if target_file.exists():
                logger.info(f"Target file already exists, skipping: {target_file}")
                # Create a job to track that we skipped this file
                job = ConversionJob(
                    source_path=source_file,
                    target_path=target_file,
                    source_format=source_file.suffix.lower(),
                    target_format=target_format,
                    quality=quality,
                    status="completed",
                    was_skipped=True,
                )
                jobs.append(job)
                continue

            # Convert file
            job = self.convert_audio_with_playlist_logic(
                source_file, target_file, quality
            )
            jobs.append(job)

        completed = len([j for j in jobs if j.status == "completed"])
        failed = len([j for j in jobs if j.status == "failed"])

        logger.info(f"Conversion complete: {completed} successful, {failed} failed")

        return jobs

    def convert_directory_with_playlist_reporting(
        self,
        source_dir: Path,
        target_dir: Path,
        target_format: str = ".mp3",
        quality: str = "2",
    ) -> dict[str, List[ConversionJob]]:
        """Convert all audio files with playlist-based reporting.

        Args:
            source_dir: Source directory
            target_dir: Target directory
            target_format: Target file format (e.g., ".mp3")
            quality: Audio quality setting

        Returns:
            Dictionary mapping playlist names to lists of ConversionJob objects
        """
        logger.info(f"Converting files from {source_dir} to {target_dir}")

        playlist_jobs: dict[str, List[ConversionJob]] = {}
        source_files: list[Path] = []

        # Collect all source files
        for ext in [".m4a", ".mp4"]:
            source_files.extend(source_dir.rglob(f"*{ext}"))

        for source_file in source_files:
            # Calculate relative path and target path
            relative_path = source_file.relative_to(source_dir)
            target_file = target_dir / relative_path.with_suffix(target_format)

            # Extract playlist name from relative path
            # Handle structure like: Playlists/PLAYLIST_NAME/track.m4a
            if len(relative_path.parts) > 1 and relative_path.parts[0] == "Playlists":
                playlist_name = relative_path.parts[1]
            else:
                # Direct structure like: PLAYLIST_NAME/track.m4a
                playlist_name = (
                    relative_path.parts[0] if relative_path.parts else "Unknown"
                )

            if playlist_name not in playlist_jobs:
                playlist_jobs[playlist_name] = []

            # Check if file exists in both directories (playlist-based logic)
            if target_file.exists():
                logger.info(f"Target file already exists, skipping: {target_file}")
                # Create a job to track that we skipped this file
                job = ConversionJob(
                    source_path=source_file,
                    target_path=target_file,
                    source_format=source_file.suffix.lower(),
                    target_format=target_format,
                    quality=quality,
                    status="completed",
                    was_skipped=True,
                )
                playlist_jobs[playlist_name].append(job)
                continue

            # Convert file
            job = self.convert_audio_with_playlist_logic(
                source_file, target_file, quality
            )
            playlist_jobs[playlist_name].append(job)

        # Log summary by playlist
        for playlist_name, jobs in playlist_jobs.items():
            converted = len(
                [j for j in jobs if j.status == "completed" and not j.was_skipped]
            )
            skipped = len([j for j in jobs if j.was_skipped])
            failed = len([j for j in jobs if j.status == "failed"])

            logger.info(
                f"Playlist '{playlist_name}': {converted} converted, "
                f"{skipped} skipped, {failed} failed"
            )

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
            logger.warning(f"File does not exist: {file_path}")
            return False

        if interactive:
            confirm = input(f"Delete {file_path}? [y/N]: ").strip().lower()
            if confirm not in ["y", "yes"]:
                logger.info("Deletion cancelled by user")
                return False

        try:
            file_path.unlink()
            logger.info(f"Deleted: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")
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
            logger.warning(f"Failed to create Track from {file_info.path}: {e}")
            return None
