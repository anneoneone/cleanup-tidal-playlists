"""File operations service for audio file management and conversion."""

import logging
import subprocess
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
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-i",
                str(source_path),
                "-q:a",
                quality,
                str(target_path),
            ]

            subprocess.run(
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

            # Convert file
            job = self.convert_audio(source_file, target_file, quality)
            jobs.append(job)

        completed = len([j for j in jobs if j.status == "completed"])
        failed = len([j for j in jobs if j.status == "failed"])

        logger.info(f"Conversion complete: {completed} successful, {failed} failed")

        return jobs

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
