"""Rekordbox database access and track content creation."""

import logging
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

from mutagen import File as MutagenFile

try:
    from pyrekordbox import Rekordbox6Database

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    Rekordbox6Database = None

from ...database.models import Track

logger = logging.getLogger(__name__)


class RekordboxGenerationError(Exception):
    """Raised when a Rekordbox operation fails."""

    pass


class RekordboxService:
    """Access to the Rekordbox database and track content creation."""

    def __init__(self, config: Any = None) -> None:
        """Initialize Rekordbox service."""
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

    def _reuse_content_by_path(self, track_path: Path) -> Optional[Any]:
        """Check for an existing DjmdContent by exact file path."""
        if not self.db:
            return None

        with suppress(Exception):
            existing = self.db.get_content(FolderPath=str(track_path)).first()
            if existing:
                logger.debug("Reusing content by path: %s", track_path)
                return existing
        return None

    def _build_enriched_payload(
        self, track: Track, track_path: Path, genre: Optional[str]
    ) -> Dict[str, Any]:
        """Build DjmdContent payload from Tidal metadata and file metadata."""
        base_meta = self._extract_track_metadata(track_path)
        payload = self._build_payload_from_track(track, base_meta)

        if genre:
            payload.update(self._apply_genre(payload, genre))
            logger.debug("Applying genre '%s' to content for %s", genre, track_path)

        assoc = self._enrich_artist_album_from_names(
            artist_name=track.artist or "Unknown Artist",
            album_name=track.album or "Unknown Album",
            release_year=track.year,
        )
        payload.update(assoc)

        return payload

    def _add_content_with_fallback(
        self,
        track_path: Path,
        payload: Dict[str, Any],
        *,
        minimal_title: str,
        log_prefix: str,
    ) -> Optional[Any]:
        """Add content with fallback to minimal payload when rich insert fails."""
        if not self.db:
            return None

        if not track_path.is_absolute():
            track_path = track_path.resolve()

        if not track_path.exists():
            logger.warning("Skipping %s add; file missing: %s", log_prefix, track_path)
            return None

        allowed_ext = {".mp3", ".m4a", ".flac", ".wav", ".aiff", ".aif"}
        if track_path.suffix.lower() not in allowed_ext:
            logger.warning(
                "Skipping %s add; unsupported file type: %s", log_prefix, track_path
            )
            return None

        sanitized = self._sanitize_content_payload(payload)
        if "Title" not in sanitized or not sanitized["Title"]:
            sanitized["Title"] = minimal_title or track_path.stem

        try:
            new_content = self.db.add_content(str(track_path), **sanitized)
            if new_content:
                logger.debug("Added %s: %s", log_prefix, track_path)
            return new_content
        except Exception as exc:
            logger.error("Failed to add %s for %s: %s", log_prefix, track_path, exc)

        minimal_payload = {"Title": minimal_title}
        with suppress(Exception):
            fallback = self.db.add_content(str(track_path), **minimal_payload)
            if fallback:
                logger.info(
                    "Added %s with minimal metadata after failure: %s",
                    log_prefix,
                    track_path,
                )
                return fallback

        logger.warning("Fallback add_content failed for %s", track_path)
        return None

    def _sanitize_content_payload(  # noqa: C901
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Filter and coerce payload to match pyrekordbox DjmdContent expectations."""
        try:
            from pyrekordbox.db6 import tables

            valid_keys = set(tables.DjmdContent.columns())
        except Exception:
            # Minimal set we rely on; prevents passing unexpected kwargs
            valid_keys = {
                "Title",
                "ArtistID",
                "AlbumID",
                "GenreID",
                "BPM",
                "Length",
                "TrackNo",
                "BitRate",
                "BitDepth",
                "Commnt",
                "FileType",
                "Rating",
                "ReleaseYear",
                "RemixerID",
                "LabelID",
                "OrgArtistID",
                "KeyID",
                "StockDate",
                "ColorID",
                "DJPlayCount",
                "ImagePath",
                "MasterDBID",
                "MasterSongID",
                "AnalysisDataPath",
                "SearchStr",
                "FileSize",
                "DiscNo",
                "ComposerID",
                "Subtitle",
                "SampleRate",
                "DisableQuantize",
                "Analysed",
                "ReleaseDate",
                "DateCreated",
                "ContentLink",
                "Tag",
                "ModifiedByRBM",
                "HotCueAutoLoad",
                "DeliveryControl",
                "DeliveryComment",
                "CueUpdated",
                "AnalysisUpdated",
                "TrackInfoUpdated",
                "Lyricist",
                "ISRC",
                "SamplerTrackInfo",
                "SamplerPlayOffset",
                "SamplerGain",
                "VideoAssociate",
                "LyricStatus",
                "ServiceID",
                "OrgFolderPath",
                "Reserved1",
                "Reserved2",
                "Reserved3",
                "Reserved4",
                "ExtInfo",
            }

        int_fields = {
            "BPM",
            "Length",
            "TrackNo",
            "BitRate",
            "BitDepth",
            "Rating",
            "ReleaseYear",
            "FileSize",
            "DiscNo",
            "SampleRate",
            "DisableQuantize",
            "Analysed",
            "SamplerTrackInfo",
            "SamplerPlayOffset",
            "LyricStatus",
            "ServiceID",
        }

        float_fields = {"SamplerGain"}
        max_len_255 = {
            "Title",
            "FolderPath",
            "FileNameL",
            "FileNameS",
            "Commnt",
            "Subtitle",
            "ImagePath",
            "AnalysisDataPath",
            "SearchStr",
            "OrgFolderPath",
        }

        sanitized: Dict[str, Any] = {}
        for key, value in payload.items():
            if key not in valid_keys:
                continue

            if value is None:
                continue

            if key in int_fields:
                try:
                    sanitized[key] = int(value)
                except (TypeError, ValueError):
                    logger.debug("Dropping %s; expected int, got %s", key, value)
                continue

            if key in float_fields:
                try:
                    sanitized[key] = float(value)
                except (TypeError, ValueError):
                    logger.debug("Dropping %s; expected float, got %s", key, value)
                continue

            if isinstance(value, (str, Path)):
                val_str = str(value)
                if key in max_len_255 and len(val_str) > 255:
                    val_str = val_str[:255]
                sanitized[key] = val_str
                continue

            sanitized[key] = value

        return sanitized

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
            existing = self._reuse_content_by_path(track_path)
            if existing:
                return existing

            candidate = self._find_existing_content(
                title=track.title,
                artist_name=track.artist or None,
                isrc=track.isrc or None,
            )
            if candidate is not None:
                return candidate

            payload = self._build_enriched_payload(track, track_path, genre)
            return self._add_content_with_fallback(
                track_path,
                payload,
                minimal_title=track.title or track_path.stem,
                log_prefix="Tidal-enriched content",
            )

        except Exception as outer_exc:
            logger.error(
                "Failed to get or create content from track for %s: %s",
                track_path,
                outer_exc,
            )
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
        """Add genre to payload, handling objects or plain strings from DB helpers."""
        updates: Dict[str, Any] = {"Genre": genre, "GenreName": genre}

        if self.db and hasattr(self.db, "get_genre") and hasattr(self.db, "add_genre"):
            with suppress(Exception):
                entry = self.db.get_genre(Name=genre).first()
                if entry is None:
                    entry = self.db.add_genre(name=genre)

                # entry can be a DB row or a plain string depending on adapter
                if entry and hasattr(entry, "ID"):
                    updates["GenreID"] = entry.ID

                name_value = getattr(entry, "Name", None)
                if not name_value and isinstance(entry, str):
                    name_value = entry
                if name_value:
                    updates["GenreName"] = name_value

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
                    logger.debug("Reusing content by ISRC: %s", isrc)
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
                        logger.debug(
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
                    logger.debug("Reusing content by Title: %s", title)
                    return by_title

        return None

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

    def close(self) -> None:
        """Close database connection."""
        if self._db:
            self._db.close()
            self._db = None
