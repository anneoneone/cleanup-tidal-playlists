"""Rekordbox XML generation and database management service."""

import logging
import xml.etree.ElementTree as ET  # noqa: S405
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

from ...database.models import Track
from .playlist_sync import RekordboxPlaylistSynchronizer

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
                logger.error("Failed to connect to Rekordbox database: %s", e)
                return None

        return self._db

    def sync_playlist_with_mytags(
        self, playlist_name: str, emoji_config_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Synchronize a playlist from MP3 folder to Rekordbox with MyTag management.

        This is the new refactored method that:
        1. Validates MP3 playlist folder exists
        2. Parses playlist name for emoji-based metadata
        3. Creates/updates Rekordbox playlist
        4. Adds missing tracks with MyTags
        5. Removes extra tracks and their MyTags
        6. Deletes playlist if empty after sync

        Args:
            playlist_name: Name of the playlist (folder name in MP3 playlists)
            emoji_config_path: Path to emoji mapping config (uses default if None)

        Returns:
            Dictionary with sync results

        Raises:
            RuntimeError: If database or config is not available
        """
        if not self.db:
            raise RuntimeError("Database connection not available")

        if not self.config:
            raise RuntimeError("Config not available")

        # Default emoji config path
        if emoji_config_path is None:
            # Try to find config relative to this file
            # Go up from src/tidal_cleanup/services/ to project root
            service_dir = Path(__file__).resolve().parent
            tidal_cleanup_dir = service_dir.parent
            src_dir = tidal_cleanup_dir.parent
            project_root = src_dir.parent
            emoji_config_path = project_root / "config" / "rekordbox_mytag_mapping.json"

            # If that doesn't exist, try alternative location
            if not emoji_config_path.exists():
                # Maybe we're in an installed package, look in cwd
                cwd_config = Path.cwd() / "config" / "rekordbox_mytag_mapping.json"
                if cwd_config.exists():
                    emoji_config_path = cwd_config
                else:
                    raise RuntimeError(
                        f"Cannot find emoji config at {emoji_config_path} "
                        f"or {cwd_config}"
                    )

        # MP3 playlists root
        mp3_playlists_root = self.config.mp3_directory / "Playlists"

        # Create synchronizer
        synchronizer = RekordboxPlaylistSynchronizer(
            db=self.db,
            mp3_playlists_root=mp3_playlists_root,
            emoji_config_path=emoji_config_path,
        )

        # Perform sync
        result = synchronizer.sync_playlist(playlist_name)

        logger.info("Playlist sync completed: %s", result)
        return result

    def ensure_genre_party_folders(
        self, emoji_config_path: Optional[Path] = None
    ) -> None:
        """Pre-create all genre/party folders by scanning playlist names.

        This should be called before syncing multiple playlists to avoid
        redundant folder creation during each sync.

        Args:
            emoji_config_path: Path to emoji mapping config (uses default if None)
        """
        if not self.db:
            raise RuntimeError("Database connection not available")

        if not self.config:
            raise RuntimeError("Config not available")

        # Default emoji config path
        if emoji_config_path is None:
            service_dir = Path(__file__).resolve().parent
            tidal_cleanup_dir = service_dir.parent
            src_dir = tidal_cleanup_dir.parent
            project_root = src_dir.parent
            emoji_config_path = project_root / "config" / "rekordbox_mytag_mapping.json"

            if not emoji_config_path.exists():
                cwd_config = Path.cwd() / "config" / "rekordbox_mytag_mapping.json"
                if cwd_config.exists():
                    emoji_config_path = cwd_config
                else:
                    raise RuntimeError(
                        f"Cannot find emoji config at {emoji_config_path} "
                        f"or {cwd_config}"
                    )

        # MP3 playlists root
        mp3_playlists_root = self.config.mp3_directory / "Playlists"

        # Create synchronizer
        synchronizer = RekordboxPlaylistSynchronizer(
            db=self.db,
            mp3_playlists_root=mp3_playlists_root,
            emoji_config_path=emoji_config_path,
        )

        # Ensure folders exist
        synchronizer.ensure_folders_exist()

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
            logger.debug("Playlist '%s' not found: %s", name, e)
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
            logger.info("Created playlist: %s", name)

            # Add tracks to the playlist
            added_count = 0
            for track_path in tracks:
                if self._add_track_to_playlist(playlist, track_path):
                    added_count += 1

            # Commit changes
            self.db.commit()
            logger.info("Added %d tracks to playlist '%s'", added_count, name)

            return playlist

        except Exception as e:
            logger.error("Failed to create playlist '%s': %s", name, e)
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
            logger.info(
                "Updated playlist '%s' with %d tracks", playlist.Name, added_count
            )

            return playlist

        except Exception as e:
            logger.error("Failed to update playlist '%s': %s", playlist.Name, e)
            if self.db:
                self.db.rollback()
            return None

    def get_or_create_content(self, track_path: Path) -> Optional[Any]:
        """Retrieve existing Rekordbox content or add it if missing.

        Improved logic:
        1) Look up by exact FolderPath
        2) If not found, attempt a fallback lookup by Title
           (helps reuse existing entries when the file path changed)
        3) If still not found, add new content with extracted metadata
           and enrich Artist/Album associations from ID3 tags if available
        """
        if not self.db:
            logger.error("Database not available")
            return None

        try:
            existing_content = self.db.get_content(FolderPath=str(track_path)).first()
            if existing_content:
                return existing_content

            metadata = self._extract_track_metadata(track_path)

            # Try reuse by ISRC or Title+Artist using ID3 tags
            title_for_lookup: Optional[str] = metadata.get("Title")
            artist_for_lookup: Optional[str] = None
            isrc_for_lookup: Optional[str] = None

            with suppress(Exception):
                from mutagen.id3 import ID3

                audio = ID3(str(track_path))
                title_for_lookup = (
                    str(audio.get("TIT2", title_for_lookup or "")).strip()
                    or title_for_lookup
                )
                artist_for_lookup = str(audio.get("TPE1", "")).strip() or None
                isrc_for_lookup = str(audio.get("TSRC", "")).strip() or None

            candidate = self._find_existing_content(
                title_for_lookup, artist_for_lookup, isrc_for_lookup
            )
            if candidate is not None:
                return candidate

            enrich = self._enrich_artist_album(track_path, metadata)

            payload: Dict[str, Any] = {**metadata}
            payload.update(enrich)

            new_content = self.db.add_content(str(track_path), **payload)
            if new_content:
                logger.info("Added new content to Rekordbox: %s", track_path)
            return new_content

        except Exception as exc:
            logger.error("Failed to add content for %s: %s", track_path, exc)
            if self.db:
                self.db.rollback()
            return None

    def get_or_create_content_from_track(
        self, track: Track, track_path: Path, genre: Optional[str] = None
    ) -> Optional[Any]:
        """Use Tidal track metadata to create/reuse Rekordbox content.

        Args:
            track: Database `Track` instance with Tidal metadata
            track_path: Absolute path to audio file

        Returns:
            DjmdContent instance or None
        """
        if not self.db:
            logger.error("Database not available")
            return None

        try:
            # Reuse by path first
            existing = self.db.get_content(FolderPath=str(track_path)).first()
            if existing:
                return existing

            # Reuse by ISRC / Title+Artist / Title
            candidate = self._find_existing_content(
                title=track.title,
                artist_name=track.artist or None,
                isrc=track.isrc or None,
            )
            if candidate is not None:
                return candidate

            # Build payload from Tidal metadata
            base_meta = self._extract_track_metadata(track_path)
            payload = self._build_payload_from_track(track, base_meta)
            if genre:
                payload.update(self._apply_genre(payload, genre))
                logger.info("Applying genre '%s' to content for %s", genre, track_path)

            # Ensure associations from Tidal names
            assoc = self._enrich_artist_album_from_names(
                artist_name=track.artist or "Unknown Artist",
                album_name=track.album or "Unknown Album",
                release_year=track.year,
            )
            payload.update(assoc)

            # Add content
            new_content = self.db.add_content(str(track_path), **payload)
            if new_content:
                logger.info("Added new content (Tidal-enriched): %s", track_path)
            return new_content

        except Exception as exc:
            logger.error(
                "Failed to add Tidal-enriched content for %s: %s", track_path, exc
            )
            if self.db:
                self.db.rollback()
            return None

    def refresh_playlist(self, playlist: Any) -> Any:
        """Reload a playlist with its latest songs from the database."""
        if not self.db:
            return playlist

        try:
            refreshed = self.db.get_playlist(ID=playlist.ID).first()
            return refreshed if refreshed else playlist
        except Exception as exc:
            logger.debug("Failed to refresh playlist %s: %s", playlist.Name, exc)
            return playlist

    def _add_track_to_playlist(self, playlist: Any, track_path: Path) -> bool:
        """Add a single track to a playlist, reusing existing content when possible.

        Args:
            playlist: Playlist object to add to
            track_path: Path to the track file

        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False

        try:
            content = self.get_or_create_content(track_path)
            if not content:
                logger.warning("Failed to resolve or create content: %s", track_path)
                return False
            self.db.add_to_playlist(playlist, content)
            return True

        except Exception as e:
            logger.warning("Failed to add track %s to playlist: %s", track_path, e)
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
            logger.warning("Failed to extract metadata from %s: %s", file_path, e)

        return metadata

    def _build_payload_from_track(
        self, track: Track, base: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge Tidal track fields into DjmdContent payload (low complexity)."""
        payload: Dict[str, Any] = {**base}
        payload.update(self._map_core_fields(track))
        payload["Commnt"] = self._compose_comments(track, payload.get("Commnt"))
        return payload

    def _map_core_fields(self, track: Track) -> Dict[str, Any]:
        """Map essential Tidal fields to DjmdContent columns."""
        core: Dict[str, Any] = {"Title": track.title}
        if track.year:
            core["ReleaseYear"] = int(track.year)
        elif track.album_release_date:
            core["ReleaseYear"] = int(track.album_release_date.year)
        if track.track_number is not None:
            core["TrackNo"] = int(track.track_number)
        if track.volume_number is not None:
            core["DiscNo"] = int(track.volume_number)
        if track.isrc:
            core["ISRC"] = track.isrc
        if track.version:
            core["Subtitle"] = track.version
        return core

    def _compose_comments(self, track: Track, existing: Optional[str]) -> str:
        """Compose comments string from Tidal fields and existing comments."""
        parts: List[str] = []
        if existing:
            parts.append(str(existing))
        if track.album_upc:
            parts.append(f"Tidal UPC: {track.album_upc}")
        if track.audio_quality:
            parts.append(f"Tidal quality: {track.audio_quality}")
        if track.audio_modes:
            parts.append(f"Tidal mode: {track.audio_modes}")
        if track.popularity is not None:
            parts.append(f"Tidal popularity: {track.popularity}")
        if track.explicit is not None:
            parts.append(f"Explicit: {bool(track.explicit)}")
        return " | ".join(parts) if parts else ""

    def _apply_genre(self, payload: Dict[str, Any], genre: str) -> Dict[str, Any]:
        """Add genre to payload, using GenreID/Name when available."""
        updates: Dict[str, Any] = {"Genre": genre}
        if self.db and hasattr(self.db, "get_genre") and hasattr(self.db, "add_genre"):
            with suppress(Exception):
                if self.db is not None:
                    entry = self.db.get_genre(Name=genre).first()
                    if entry is None:
                        entry = self.db.add_genre(name=genre)
                    if entry and hasattr(entry, "ID"):
                        updates["GenreID"] = entry.ID
                    if entry and hasattr(entry, "Name"):
                        updates["GenreName"] = entry.Name
        else:
            updates["GenreName"] = genre
        return updates

    def _enrich_artist_album_from_names(
        self, artist_name: str, album_name: str, release_year: Optional[int]
    ) -> Dict[str, Any]:
        """Ensure Artist/Album associations from provided names."""
        result: Dict[str, Any] = {}
        if self.db is None:
            return result

        with suppress(Exception):
            artist = self.db.get_artist(Name=artist_name).first()
            if artist is None:
                artist = self.db.add_artist(name=artist_name)
            artist_id = getattr(artist, "ID", None)
            if artist_id:
                result["ArtistID"] = artist_id

            album = self.db.get_album(Name=album_name).first()
            if album is None:
                album = self.db.add_album(name=album_name)
            album_id = getattr(album, "ID", None)
            if album_id:
                result["AlbumID"] = album_id

        if release_year is not None:
            result["ReleaseYear"] = int(release_year)
        return result

    def _find_existing_content(
        self,
        title: Optional[str],
        artist_name: Optional[str],
        isrc: Optional[str],
    ) -> Optional[Any]:
        """Find existing content by ISRC or Title+Artist, then Title only."""
        if not self.db:
            return None

        # ISRC is the strongest identifier when present
        if isrc:
            with suppress(Exception):
                by_isrc = self.db.get_content(ISRC=isrc).first()
                if by_isrc:
                    logger.info("Reusing content by ISRC: %s", isrc)
                    return by_isrc

        # Title + Artist via associations
        if title and artist_name:
            with suppress(Exception):
                artist = self.db.get_artist(Name=artist_name).first()
                if artist:
                    content = self.db.get_content(
                        Title=title, ArtistID=artist.ID
                    ).first()
                    if content:
                        logger.info(
                            "Reusing content by Title+Artist: %s - %s",
                            title,
                            artist_name,
                        )
                        return content

        # Title only as a weaker fallback
        if title:
            with suppress(Exception):
                by_title = self.db.get_content(Title=title).first()
                if by_title:
                    logger.info("Reusing content by Title: %s", title)
                    return by_title

        return None

    def _enrich_artist_album(
        self, track_path: Path, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create or reuse Artist/Album and return association IDs.

        Returns a dict containing optional keys: ArtistID, AlbumID, ReleaseYear
        """
        artist_id: Optional[str] = None
        album_id: Optional[str] = None
        release_year = metadata.get("ReleaseYear") or None

        with suppress(Exception):
            from mutagen.id3 import ID3

            audio = ID3(str(track_path))
            artist_name = str(audio.get("TPE1", "")).strip() or "Unknown Artist"
            album_name = str(audio.get("TALB", "")).strip() or "Unknown Album"
            year_str = str(audio.get("TDRC", "")).strip()
            if year_str and not release_year:
                release_year = int(year_str[:4])

            if self.db is not None:
                artist = self.db.get_artist(Name=artist_name).first()
                if artist is None:
                    artist = self.db.add_artist(name=artist_name)
                artist_id = getattr(artist, "ID", None)

                album = self.db.get_album(Name=album_name).first()
                if album is None:
                    album = self.db.add_album(name=album_name)
                album_id = getattr(album, "ID", None)

        result: Dict[str, Any] = {}
        if artist_id:
            result["ArtistID"] = artist_id
        if album_id:
            result["AlbumID"] = album_id
        if release_year is not None:
            result["ReleaseYear"] = release_year
        return result

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
                    val = audio_file[key][0]
                    metadata["ReleaseYear"] = converter(val)
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
                    val = audio_file[key][0]
                    metadata["BPM"] = converter(val)
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
                    val = audio_file[key][0]
                    metadata["ReleaseYear"] = converter(val)
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
                    val = audio_file[key][0]
                    metadata["BPM"] = converter(val)
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
            logger.info("Generating Rekordbox XML from %s", input_folder)

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

            logger.info("Successfully generated Rekordbox XML: %s", output_file)
            logger.info(
                f"Processed {len(self.track_data)} tracks from "
                f"{playlist_count} playlists"
            )

        except Exception as e:
            logger.error("Failed to generate Rekordbox XML: %s", e)
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
        logger.debug("Processing playlist: %s", playlist_name)

        # Supported audio extensions
        audio_extensions = {".mp3", ".wav", ".flac", ".aac"}

        for file_path in sorted(folder_path.iterdir()):
            if file_path.suffix.lower() in audio_extensions:
                try:
                    self._process_audio_file(file_path, playlist_name)
                except Exception as e:
                    logger.warning("Failed to process %s: %s", file_path, e)
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
                logger.warning("Cannot read audio file: %s", file_path)
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
            logger.warning("Cannot process audio file %s: %s", file_path, e)

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
