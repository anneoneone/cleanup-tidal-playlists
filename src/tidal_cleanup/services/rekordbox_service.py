"""Rekordbox XML generation service."""

import logging
import xml.etree.ElementTree as ET  # nosec B405 - XML generation only
from pathlib import Path
from typing import Any, Dict

from mutagen import File as MutagenFile  # type: ignore[attr-defined]
from mutagen.mp3 import HeaderNotFoundError

logger = logging.getLogger(__name__)


class RekordboxGenerationError(Exception):
    """Custom exception for Rekordbox XML generation errors."""

    pass


class RekordboxService:
    """Service for generating Rekordbox XML files."""

    def __init__(self) -> None:
        """Initialize Rekordbox service."""
        self.track_data: Dict[str, dict[str, Any]] = {}
        self.track_id_counter = 1

    def generate_xml(
        self, input_folder: Path, output_file: Path, rekordbox_version: str = "7.0.4"
    ) -> None:
        """Generate Rekordbox XML from audio files in input folder.

        Args:
            input_folder: Folder containing playlist subfolders
            output_file: Output XML file path
            rekordbox_version: Rekordbox version for XML header

        Raises:
            RekordboxGenerationError: If generation fails
        """
        if not input_folder.exists():
            raise RekordboxGenerationError(
                f"Input folder does not exist: {input_folder}"
            )

        try:
            logger.info(f"Generating Rekordbox XML from {input_folder}")

            # Reset state
            self.track_data = {}
            self.track_id_counter = 1

            # Create XML structure
            root = self._create_xml_root(rekordbox_version)
            collection = root.find("COLLECTION")
            playlists_node = root.find("PLAYLISTS")

            if collection is None or playlists_node is None:
                raise RekordboxGenerationError("Failed to create XML structure")

            root_playlist_node = playlists_node.find("NODE")
            if root_playlist_node is None:
                raise RekordboxGenerationError("Failed to find root playlist node")

            # Process all playlist folders
            playlist_count = 0
            for playlist_folder in sorted(input_folder.iterdir()):
                if playlist_folder.is_dir():
                    self._process_playlist_folder(playlist_folder)
                    playlist_count += 1

            # Add tracks to collection
            for track_info in self.track_data.values():
                track_element = ET.SubElement(collection, "TRACK")
                for attr, value in track_info.items():
                    track_element.set(attr, str(value))

            # Update counters
            collection.set("Entries", str(len(self.track_data)))
            root_playlist_node.set("Count", str(playlist_count))

            # Write XML file
            self._write_xml_file(root, output_file)

            logger.info(f"Successfully generated Rekordbox XML: {output_file}")
            logger.info(
                f"Processed {len(self.track_data)} tracks from "
                f"{playlist_count} playlists"
            )

        except Exception as e:
            logger.error(f"Failed to generate Rekordbox XML: {e}")
            raise RekordboxGenerationError(f"XML generation failed: {e}")

    def _create_xml_root(self, version: str) -> ET.Element:
        """Create root XML element with proper structure.

        Args:
            version: Rekordbox version

        Returns:
            Root XML element
        """
        dj_playlists = ET.Element("DJ_PLAYLISTS", Version="1.0.0")

        ET.SubElement(
            dj_playlists,
            "PRODUCT",
            Name="rekordbox",
            Version=version,
            Company="AlphaTheta",
        )

        ET.SubElement(dj_playlists, "COLLECTION", Entries="0")
        playlists = ET.SubElement(dj_playlists, "PLAYLISTS")

        ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="0")

        return dj_playlists

    def _process_playlist_folder(self, folder_path: Path) -> None:
        """Process a single playlist folder.

        Args:
            folder_path: Path to playlist folder
        """
        playlist_name = folder_path.name
        logger.debug(f"Processing playlist: {playlist_name}")

        # Supported audio extensions
        audio_extensions = {".mp3", ".wav", ".flac", ".aac"}

        for file_path in sorted(folder_path.iterdir()):
            if file_path.suffix.lower() in audio_extensions:
                try:
                    self._process_audio_file(file_path, playlist_name)
                except Exception as e:
                    logger.warning(f"Failed to process {file_path}: {e}")
                    continue

    def _process_audio_file(self, file_path: Path, playlist_name: str) -> None:
        """Process a single audio file.

        Args:
            file_path: Path to audio file
            playlist_name: Name of containing playlist
        """
        try:
            # Try to get metadata
            audio_file = MutagenFile(file_path, easy=True)
            if not audio_file:
                logger.warning(f"Cannot read audio file: {file_path}")
                return

            # Extract metadata
            track_name = self._get_metadata_value(audio_file, "title", file_path.stem)
            artist = self._get_metadata_value(audio_file, "artist", "Unknown Artist")
            album = self._get_metadata_value(audio_file, "album", "Unknown Album")
            genre = self._get_metadata_value(audio_file, "genre", "")

            # Get version from playlist name
            version = self._get_version_from_playlist(playlist_name)

            # Create unique key for track
            track_key = f"{track_name}_{artist}_{album}"

            # Create file location URL
            location = f"file://localhost/{file_path.as_posix()}"

            if track_key in self.track_data:
                # Track already exists, update comments and version
                existing = self.track_data[track_key]
                existing["Comments"] += f" //{playlist_name}//"
                if version:
                    existing["Mix"] = self._merge_versions(
                        existing.get("Mix", ""), version
                    )
            else:
                # New track
                self.track_data[track_key] = {
                    "TrackID": str(self.track_id_counter),
                    "Name": track_name,
                    "Artist": artist,
                    "Album": album,
                    "Genre": genre,
                    "Mix": version,
                    "Location": location,
                    "Comments": f"//{playlist_name}//",
                }
                self.track_id_counter += 1

        except (HeaderNotFoundError, Exception) as e:
            logger.warning(f"Cannot process audio file {file_path}: {e}")

    def _get_metadata_value(self, audio_file: Any, key: str, default: str = "") -> str:
        """Get metadata value from audio file.

        Args:
            audio_file: Mutagen audio file object
            key: Metadata key to retrieve
            default: Default value if key not found

        Returns:
            Metadata value or default
        """
        try:
            value = audio_file.get(key, [default])
            if isinstance(value, list) and value:
                return str(value[0])
            return str(value) if value else default
        except Exception:
            return default

    def _get_version_from_playlist(self, playlist_name: str) -> str:
        """Extract version information from playlist name.

        Args:
            playlist_name: Name of playlist

        Returns:
            Version string based on playlist name patterns
        """
        name_upper = playlist_name.upper()

        if " D " in name_upper:
            return "Digital"
        elif " V " in name_upper:
            return "Vinyl"
        elif " R " in name_upper:
            return "Recherche"
        elif " O " in name_upper:
            return "Old"

        return ""

    def _merge_versions(self, existing: str, new: str) -> str:
        """Merge version strings, preferring new over existing.

        Args:
            existing: Existing version string
            new: New version string

        Returns:
            Merged version string
        """
        return new if new else existing

    def _write_xml_file(self, root: ET.Element, output_file: Path) -> None:
        """Write XML tree to file.

        Args:
            root: Root XML element
            output_file: Output file path
        """
        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Create tree and write
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding="UTF-8", xml_declaration=True)

    def validate_input_folder(self, folder_path: Path) -> bool:
        """Validate that input folder contains playlist subfolders.

        Args:
            folder_path: Folder to validate

        Returns:
            True if folder is valid for Rekordbox generation
        """
        if not folder_path.exists():
            return False

        if not folder_path.is_dir():
            return False

        # Check if folder contains subdirectories (playlists)
        has_playlists = any(item.is_dir() for item in folder_path.iterdir())

        return has_playlists

    def get_track_count_estimate(self, input_folder: Path) -> int:
        """Estimate number of tracks that will be processed.

        Args:
            input_folder: Input folder path

        Returns:
            Estimated track count
        """
        if not self.validate_input_folder(input_folder):
            return 0

        audio_extensions = {".mp3", ".wav", ".flac", ".aac"}
        count = 0

        for playlist_folder in input_folder.iterdir():
            if playlist_folder.is_dir():
                for file_path in playlist_folder.iterdir():
                    if file_path.suffix.lower() in audio_extensions:
                        count += 1

        return count
