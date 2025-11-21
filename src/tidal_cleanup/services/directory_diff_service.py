"""Generic directory comparison and diff service.

This service provides a reusable mechanism to compare two directories and identify:
- Files that exist only in the source (need to be processed/added)
- Files that exist only in the target (need to be removed/cleaned up)
- Files that exist in both (can be skipped)

This is useful for optimizing operations like:
- Converting audio files (M4A → MP3): only convert missing files, delete orphaned MP3s
- Syncing playlists: only add/remove tracks that differ between directories and database
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# @convert _scan_directory()
@dataclass
class FileIdentity:
    """Represents a file's identity for comparison purposes.

    Attributes:
        key: Unique identifier for the file (e.g., stem or (title, artist))
        path: Absolute path to the file
        metadata: Optional additional metadata (e.g., format, size, tags)
    """

    key: str
    path: Path
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class DirectoryDiff:
    """Results of comparing two directories.

    Attributes:
        only_in_source: Files only in source (need to be added/processed)
        only_in_target: Files only in target (need to be removed)
        in_both: Files that exist in both directories (can be skipped)
        source_identities: Full identity mapping for source files
        target_identities: Full identity mapping for target files
    """

    only_in_source: Set[str]
    only_in_target: Set[str]
    in_both: Set[str]
    source_identities: Dict[str, FileIdentity]
    target_identities: Dict[str, FileIdentity]

    def __repr__(self) -> str:
        """String representation of diff results."""
        return (
            f"DirectoryDiff(to_add={len(self.only_in_source)}, "
            f"to_remove={len(self.only_in_target)}, "
            f"existing={len(self.in_both)})"
        )


class DirectoryDiffService:
    """Service for comparing directories and computing differences."""

    def __init__(self) -> None:
        """Initialize the directory diff service."""
        pass

    def compare_directories(
        self,
        source_dir: Path,
        target_dir: Path,
        source_extensions: Tuple[str, ...] = (".m4a", ".mp4"),
        target_extensions: Tuple[str, ...] = (".mp3",),
        identity_fn: Optional[Callable[[Path], str]] = None,
    ) -> DirectoryDiff:
        """Compare two directories and compute differences.

        Args:
            source_dir: Source directory to compare from
            target_dir: Target directory to compare to
            source_extensions: File extensions to consider in source directory
            target_extensions: File extensions to consider in target directory
            identity_fn: Optional function to compute file identity key.
                        Defaults to using file stem (filename without extension).

        Returns:
            DirectoryDiff object with comparison results

        Example:
            >>> diff = service.compare_directories(
            ...     Path("/music/m4a/Playlists/MyPlaylist"),
            ...     Path("/music/mp3/Playlists/MyPlaylist"),
            ...     source_extensions=(".m4a",),
            ...     target_extensions=(".mp3",)
            ... )
            >>> print(f"Need to convert: {len(diff.only_in_source)} files")
            >>> print(f"Need to delete: {len(diff.only_in_target)} files")
        """
        # Use default identity function if not provided
        if identity_fn is None:

            def identity_fn(p: Path) -> str:
                return p.stem

        # Scan source directory
        source_identities = self._scan_directory(
            source_dir, source_extensions, identity_fn
        )

        # Scan target directory
        target_identities = self._scan_directory(
            target_dir, target_extensions, identity_fn
        )

        # Compute differences
        source_keys = set(source_identities.keys())
        target_keys = set(target_identities.keys())

        only_in_source = source_keys - target_keys
        only_in_target = target_keys - source_keys
        in_both = source_keys & target_keys

        logger.debug(
            f"Directory diff: {len(only_in_source)} to add, "
            f"{len(only_in_target)} to remove, {len(in_both)} in both"
        )

        return DirectoryDiff(
            only_in_source=only_in_source,
            only_in_target=only_in_target,
            in_both=in_both,
            source_identities=source_identities,
            target_identities=target_identities,
        )

    def compare_directory_to_items(
        self,
        directory: Path,
        items: List[Any],
        dir_extensions: Tuple[str, ...] = (".mp3",),
        dir_identity_fn: Optional[Callable[[Path], str]] = None,
        item_identity_fn: Optional[Callable[[Any], str]] = None,
    ) -> Tuple[Set[str], Set[str], Set[str], Dict[str, FileIdentity], Dict[str, Any]]:
        """Compare a directory to a list of items (e.g., database records).

        This is useful for comparing a filesystem directory against database entries,
        such as when syncing MP3 files with Rekordbox tracks.

        Args:
            directory: Directory to scan
            items: List of items to compare against (e.g., database records)
            dir_extensions: File extensions to consider in directory
            dir_identity_fn: Function to compute identity key from file path
            item_identity_fn: Function to compute identity key from item

        Returns:
            Tuple of (only_in_dir, only_in_items, in_both, dir_identities,
            item_identities)

        Example:
            >>> only_in_dir, only_in_items, in_both, dir_ids, item_ids = \
            ...     service.compare_directory_to_items(
            ...         Path("/music/mp3/Playlists/MyPlaylist"),
            ...         rekordbox_tracks,
            ...         item_identity_fn=lambda t: (t['title'], t['artist'])
            ...     )
        """
        # Use default identity functions if not provided
        if dir_identity_fn is None:

            def dir_identity_fn(p: Path) -> str:
                return p.stem

        if item_identity_fn is None:

            def item_identity_fn(item: Any) -> str:
                return str(item)

        # Scan directory
        dir_identities = self._scan_directory(
            directory, dir_extensions, dir_identity_fn
        )

        # Build item identities
        item_identities = {}
        for item in items:
            key = item_identity_fn(item)
            item_identities[key] = item

        # Compute differences
        dir_keys = set(dir_identities.keys())
        item_keys = set(item_identities.keys())

        only_in_dir = dir_keys - item_keys
        only_in_items = item_keys - dir_keys
        in_both = dir_keys & item_keys

        logger.info(
            f"Directory-to-items diff: {len(only_in_dir)} to add, "
            f"{len(only_in_items)} to remove, {len(in_both)} in both"
        )

        return only_in_dir, only_in_items, in_both, dir_identities, item_identities

    # @convert compare_directories()
    def _scan_directory(
        self,
        directory: Path,
        extensions: Tuple[str, ...],
        identity_fn: Callable[[Path], str],
    ) -> Dict[str, FileIdentity]:
        """Scan a directory and build identity mapping.

        Args:
            directory: Directory to scan
            extensions: File extensions to include
            identity_fn: Function to compute file identity key

        Returns:
            Dictionary mapping identity keys to FileIdentity objects
        """
        identities: Dict[str, FileIdentity] = {}

        if not directory.exists() or not directory.is_dir():
            logger.warning(
                f"Directory does not exist or is not a directory: {directory}"
            )
            return identities

        # Recursively find all files with matching extensions
        for ext in extensions:
            for file_path in directory.rglob(f"*{ext}"):
                if file_path.is_file():
                    try:
                        key = identity_fn(file_path)
                        # Handle potential duplicate keys
                        if key in identities:
                            logger.warning(
                                f"Duplicate file identity '{key}': {file_path} "
                                f"and {identities[key].path}"
                            )
                        identities[key] = FileIdentity(
                            key=key, path=file_path.resolve()
                        )
                    except Exception as e:
                        logger.error(f"Error computing identity for {file_path}: {e}")

        logger.debug(f"Scanned {directory}: found {len(identities)} files")
        return identities

    # @convert convert_directory()
    def compare_by_stem_with_extension_mapping(
        self,
        source_dir: Path,
        target_dir: Path,
        source_extensions: Tuple[str, ...] = (".m4a", ".mp4"),
        target_extensions: Tuple[str, ...] = (".mp3",),
    ) -> DirectoryDiff:
        """Compare directories using file stem (filename without extension).

        This is a convenience method for the common case of comparing files
        that have the same name but different extensions (e.g., M4A → MP3).

        Args:
            source_dir: Source directory
            target_dir: Target directory
            source_extensions: Extensions to consider in source
            target_extensions: Extensions to consider in target

        Returns:
            DirectoryDiff object with comparison results
        """
        return self.compare_directories(
            source_dir=source_dir,
            target_dir=target_dir,
            source_extensions=source_extensions,
            target_extensions=target_extensions,
            identity_fn=lambda p: p.stem,
        )
