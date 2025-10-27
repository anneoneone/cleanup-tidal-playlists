"""Rekordbox XML generation and database management service."""

import logging
import xml.etree.ElementTree as ET  # nosec B405 - XML generation only
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

from mutagen import File as MutagenFile
from mutagen.mp3 import HeaderNotFoundError

try:
    from pyrekordbox import Rekordbox6Database

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    Rekordbox6Database = None

logger = logging.getLogger(__name__)


class RekordboxGenerationError(Exception):
    """Custom exception for Rekordbox XML generation errors."""

    pass


class RekordboxService:
    """Service for generating Rekordbox XML files and managing database."""

    def __init__(self, config: Any = None) -> None:
        """Initialize Rekordbox service."""
        self.track_data: Dict[str, dict[str, Any]] = {}
        self.track_id_counter = 1
        self.config = config
        self._db: Optional[Rekordbox6Database] = None

    @property
    def db(self) -> Optional[Rekordbox6Database]:
        """Get database connection, creating if needed."""
        if not PYREKORDBOX_AVAILABLE:
            logger.warning("pyrekordbox not available, database operations disabled")
            return None

        if self._db is None:
            try:
                self._db = Rekordbox6Database()
                logger.info("Connected to Rekordbox database")
            except Exception as e:
                logger.error(f"Failed to connect to Rekordbox database: {e}")
                return None

        return self._db

    def find_playlist(self, name: str) -> Optional[Any]:
        """Find a playlist in the Rekordbox database by name.

        Args:
            name: Playlist name to search for

        Returns:
            Playlist object if found, None otherwise
        """
        if not self.db:
            return None

        try:
            playlist = self.db.get_playlist(Name=name).first()
            return playlist
        except Exception as e:
            logger.debug(f"Playlist '{name}' not found: {e}")
            return None

    def create_playlist(self, name: str, tracks: List[Path]) -> Optional[Any]:
        """Create a new playlist in Rekordbox with the given tracks.

        Args:
            name: Name of the new playlist
            tracks: List of track file paths to add

        Returns:
            Created playlist object or None if failed
        """
        if not self.db:
            logger.error("Database not available")
            return None

        try:
            # Create the playlist
            playlist = self.db.create_playlist(name)
            logger.info(f"Created playlist: {name}")

            # Add tracks to the playlist
            added_count = 0
            for track_path in tracks:
                if self._add_track_to_playlist(playlist, track_path):
                    added_count += 1

            # Commit changes
            self.db.commit()
            logger.info(f"Added {added_count} tracks to playlist '{name}'")

            return playlist

        except Exception as e:
            logger.error(f"Failed to create playlist '{name}': {e}")
            if self.db:
                self.db.rollback()
            return None

    def update_playlist(self, playlist: Any, tracks: List[Path]) -> Optional[Any]:
        """Update an existing playlist with new tracks.

        Args:
            playlist: Existing playlist object
            tracks: List of track file paths to set as playlist content

        Returns:
            Updated playlist object or None if failed
        """
        if not self.db:
            logger.error("Database not available")
            return None

        try:
            # Clear existing tracks from playlist
            for song in playlist.Songs:
                self.db.remove_from_playlist(playlist, song)

            # Add new tracks
            added_count = 0
            for track_path in tracks:
                if self._add_track_to_playlist(playlist, track_path):
                    added_count += 1

            # Commit changes
            self.db.commit()
            logger.info(f"Updated playlist '{playlist.Name}' with {added_count} tracks")

            return playlist

        except Exception as e:
            logger.error(f"Failed to update playlist '{playlist.Name}': {e}")
            if self.db:
                self.db.rollback()
            return None

    def _add_track_to_playlist(self, playlist: Any, track_path: Path) -> bool:
        """Add a single track to a playlist.

        Args:
            playlist: Playlist object to add to
            track_path: Path to the track file

        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False

        try:
            # Check if track already exists in database
            existing_content = self.db.get_content(FolderPath=str(track_path)).first()

            if existing_content:
                # Track exists, add to playlist
                self.db.add_to_playlist(playlist, existing_content)
                return True
            else:
                # Track doesn't exist, add to database with full metadata
                logger.debug(f"Adding new track to database: {track_path}")

                # Extract comprehensive metadata
                metadata = self._extract_track_metadata(track_path)

                # Add content with metadata
                new_content = self.db.add_content(str(track_path), **metadata)
                if new_content:
                    logger.debug(
                        "Successfully added content with metadata, "
                        "now adding to playlist"
                    )
                    self.db.add_to_playlist(playlist, new_content)
                    return True
                else:
                    logger.warning(f"Failed to add track to database: {track_path}")
                    return False

        except Exception as e:
            logger.warning(f"Failed to add track {track_path} to playlist: {e}")
            return False

    def _extract_track_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract comprehensive metadata from an audio file for Rekordbox.

        Args:
            file_path: Path to the audio file

        Returns:
            Dictionary containing track metadata with DjmdContent field names
        """
        # Initialize with defaults - only include fields that can be set directly
        # Exclude association proxy fields (ArtistName, AlbumName, GenreName etc.)
        metadata = {
            "Title": file_path.stem,
            "ReleaseYear": 0,
            "TrackNo": 0,
            "BPM": 0,  # Will be in hundredths (multiply by 100)
            "Commnt": "",  # Comments field
            "Subtitle": "",  # Mix/version info
            "ISRC": "",
            "DiscNo": 0,
        }

        try:
            audio_file = MutagenFile(str(file_path))
            if audio_file is not None:
                # Extract metadata that can be set directly
                self._extract_direct_metadata(audio_file, metadata)
        except Exception as e:
            logger.warning(f"Failed to extract metadata from {file_path}: {e}")

        return metadata

    def _extract_direct_metadata(  # noqa: C901
        self, audio_file: Any, metadata: Dict[str, Any]
    ) -> None:
        """Extract metadata fields that can be set directly in pyrekordbox."""
        # Title
        for key in ["TIT2", "TITLE", "\xa9nam", "title"]:
            if key in audio_file:
                metadata["Title"] = str(audio_file[key][0])
                break

        # Release year
        year_keys = [
            ("TDRC", lambda x: int(str(x)[:4])),
            ("TYER", lambda x: int(str(x))),
            ("DATE", lambda x: int(str(x)[:4])),
            ("\xa9day", lambda x: int(str(x)[:4])),
            ("date", lambda x: int(str(x)[:4])),
        ]

        for key, converter in year_keys:
            if key in audio_file:
                with suppress(ValueError, IndexError):
                    metadata["ReleaseYear"] = converter(audio_file[key][0])
                    break

        # Track number
        if "TRCK" in audio_file:
            with suppress(ValueError, IndexError):
                track_info = str(audio_file["TRCK"][0]).split("/")[0]
                metadata["TrackNo"] = int(track_info)
        elif "TRACKNUMBER" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["TrackNo"] = int(str(audio_file["TRACKNUMBER"][0]))
        elif "tracknumber" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["TrackNo"] = int(str(audio_file["tracknumber"][0]))
        elif "trkn" in audio_file:
            with suppress(ValueError, IndexError, TypeError):
                metadata["TrackNo"] = int(audio_file["trkn"][0][0])

        # Disc number
        if "TPOS" in audio_file:
            with suppress(ValueError, IndexError):
                disc_info = str(audio_file["TPOS"][0]).split("/")[0]
                metadata["DiscNo"] = int(disc_info)
        elif "DISCNUMBER" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["DiscNo"] = int(str(audio_file["DISCNUMBER"][0]))
        elif "discnumber" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["DiscNo"] = int(str(audio_file["discnumber"][0]))

        # BPM (Rekordbox stores in hundredths, so multiply by 100)
        bpm_keys = [
            ("TBPM", lambda x: int(float(str(x)) * 100)),
            ("BPM", lambda x: int(float(str(x)) * 100)),
            ("bpm", lambda x: int(float(str(x)) * 100)),
            (
                "tmpo",
                lambda x: int(x) if isinstance(x, int) else int(float(str(x)) * 100),
            ),
        ]

        for key, converter in bpm_keys:
            if key in audio_file:
                with suppress(ValueError, IndexError, TypeError):
                    metadata["BPM"] = converter(audio_file[key][0])
                    break

        # Comments - collect all available info including artist/album
        comments = []

        # Add artist info to comments since we can't set ArtistName directly
        for key in ["TPE1", "ARTIST", "\xa9ART", "artist"]:
            if key in audio_file:
                artist = str(audio_file[key][0])
                comments.append(f"Artist: {artist}")
                break

        # Add album info to comments
        for key in ["TALB", "ALBUM", "\xa9alb", "album"]:
            if key in audio_file:
                album = str(audio_file[key][0])
                comments.append(f"Album: {album}")
                break

        # Add genre info to comments
        for key in ["TCON", "GENRE", "\xa9gen", "genre"]:
            if key in audio_file:
                genre = str(audio_file[key][0])
                comments.append(f"Genre: {genre}")
                break

        # Add original comments
        for key in ["COMM::eng", "COMMENT", "\xa9cmt", "comment"]:
            if key in audio_file:
                original_comment = str(audio_file[key][0])
                comments.append(original_comment)
                break

        # Add Tidal-specific info to comments
        tidal_fields = ["TXXX:URL", "TXXX:UPC", "TXXX:rating"]
        for field in tidal_fields:
            if field in audio_file:
                value = str(audio_file[field][0])
                field_name = field.split(":")[-1]
                comments.append(f"Tidal {field_name}: {value}")

        if comments:
            metadata["Commnt"] = " | ".join(comments)

        # Subtitle/Mix version
        for key in ["TIT3", "SUBTITLE", "subtitle"]:
            if key in audio_file:
                metadata["Subtitle"] = str(audio_file[key][0])
                break

        # ISRC
        for key in ["TSRC", "ISRC", "isrc"]:
            if key in audio_file:
                metadata["ISRC"] = str(audio_file[key][0])
                break

    def _extract_numeric_metadata(  # noqa: C901
        self, audio_file: Any, metadata: Dict[str, Any]
    ) -> None:
        """Extract numeric metadata fields."""
        # Release year
        year_keys = [
            ("TDRC", lambda x: int(str(x)[:4])),
            ("TYER", lambda x: int(str(x))),
            ("DATE", lambda x: int(str(x)[:4])),
            ("\xa9day", lambda x: int(str(x)[:4])),
            ("date", lambda x: int(str(x)[:4])),
        ]

        for key, converter in year_keys:
            if key in audio_file:
                with suppress(ValueError, IndexError):
                    metadata["ReleaseYear"] = converter(audio_file[key][0])
                    break

        # Track number
        if "TRCK" in audio_file:
            with suppress(ValueError, IndexError):
                track_info = str(audio_file["TRCK"][0]).split("/")[0]
                metadata["TrackNo"] = int(track_info)
        elif "TRACKNUMBER" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["TrackNo"] = int(str(audio_file["TRACKNUMBER"][0]))
        elif "tracknumber" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["TrackNo"] = int(str(audio_file["tracknumber"][0]))
        elif "trkn" in audio_file:
            with suppress(ValueError, IndexError, TypeError):
                metadata["TrackNo"] = int(audio_file["trkn"][0][0])

        # Disc number
        if "TPOS" in audio_file:
            with suppress(ValueError, IndexError):
                disc_info = str(audio_file["TPOS"][0]).split("/")[0]
                metadata["DiscNo"] = int(disc_info)
        elif "DISCNUMBER" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["DiscNo"] = int(str(audio_file["DISCNUMBER"][0]))
        elif "discnumber" in audio_file:
            with suppress(ValueError, IndexError):
                metadata["DiscNo"] = int(str(audio_file["discnumber"][0]))

        # BPM (Rekordbox stores in hundredths, so multiply by 100)
        bpm_keys = [
            ("TBPM", lambda x: int(float(str(x)) * 100)),
            ("BPM", lambda x: int(float(str(x)) * 100)),
            ("bpm", lambda x: int(float(str(x)) * 100)),
            (
                "tmpo",
                lambda x: int(x) if isinstance(x, int) else int(float(str(x)) * 100),
            ),
        ]

        for key, converter in bpm_keys:
            if key in audio_file:
                with suppress(ValueError, IndexError, TypeError):
                    metadata["BPM"] = converter(audio_file[key][0])
                    break

    def _extract_additional_metadata(
        self, audio_file: Any, metadata: Dict[str, Any]
    ) -> None:
        """Extract additional metadata specific to Tidal or other sources."""
        # Look for Tidal-specific tags
        tidal_fields = [
            "TXXX:URL",
            "TXXX:UPC",
            "TXXX:rating",
            "TXXX:major_brand",
            "TXXX:minor_version",
            "TXXX:compatible_brands",
        ]

        tidal_info = []
        for field in tidal_fields:
            if field in audio_file:
                value = str(audio_file[field][0])
                tidal_info.append(f"{field.split(':')[-1]}: {value}")

        # Append Tidal info to comments if found
        if tidal_info:
            existing_comment = metadata.get("Commnt", "")
            tidal_comment = " | ".join(tidal_info)
            if existing_comment:
                metadata["Commnt"] = f"{existing_comment} | {tidal_comment}"
            else:
                metadata["Commnt"] = tidal_comment

    def close(self) -> None:
        """Close database connection."""
        if self._db:
            self._db.close()
            self._db = None

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
