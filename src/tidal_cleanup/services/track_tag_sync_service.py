"""Service for syncing track tags based on MP3 playlist directories.

This service handles Step 2 of the sync algorithm:
- Iterates over MP3 playlist directories
- Parses directory names to extract tag metadata
- Syncs tracks with proper MyTag management
- Handles defaults for missing tags (Archived status, Tidal source)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    db6 = None

from .mytag_manager import MyTagManager
from .playlist_name_parser import PlaylistMetadata, PlaylistNameParser

logger = logging.getLogger(__name__)


class TrackTagSyncService:
    """Service for syncing track tags based on MP3 playlist structure."""

    def __init__(
        self,
        db: Any,
        mp3_playlists_root: Path,
        mytag_mapping_path: Path,
    ) -> None:
        """Initialize the service.

        Args:
            db: Rekordbox6Database instance
            mp3_playlists_root: Root directory containing MP3 playlist folders
            mytag_mapping_path: Path to rekordbox_mytag_mapping.json
        """
        if not PYREKORDBOX_AVAILABLE:
            raise RuntimeError("pyrekordbox is not available")

        self.db = db
        self.mp3_playlists_root = mp3_playlists_root
        self.mytag_manager = MyTagManager(db)
        self.name_parser = PlaylistNameParser(mytag_mapping_path)

        # Supported audio extensions
        self.audio_extensions = {".mp3", ".flac", ".wav", ".aac", ".m4a"}

    def sync_all_playlists(self) -> Dict[str, Any]:
        """Sync all MP3 playlists with Rekordbox tracks.

        Returns:
            Dictionary with sync results
        """
        logger.info("Starting track tag sync for all playlists...")

        if not self.mp3_playlists_root.exists():
            raise FileNotFoundError(
                f"MP3 playlists root does not exist: {self.mp3_playlists_root}"
            )

        results = {
            "playlists_processed": 0,
            "tracks_added": 0,
            "tracks_updated": 0,
            "tracks_removed": 0,
            "skipped_playlists": 0,
        }

        # Get all playlist directories
        playlist_dirs = [d for d in self.mp3_playlists_root.iterdir() if d.is_dir()]

        logger.info(f"Found {len(playlist_dirs)} playlist directories")

        for playlist_dir in playlist_dirs:
            playlist_name = playlist_dir.name
            logger.info(f"\nProcessing playlist: {playlist_name}")

            try:
                sync_result = self.sync_playlist(playlist_name)

                results["playlists_processed"] += 1
                results["tracks_added"] += sync_result["tracks_added"]
                results["tracks_updated"] += sync_result["tracks_updated"]
                results["tracks_removed"] += sync_result["tags_removed"]

            except Exception as e:
                logger.error(f"Failed to sync playlist '{playlist_name}': {e}")
                results["skipped_playlists"] += 1
                continue

        self.db.commit()
        logger.info("\n✓ Track tag sync completed")

        return results

    def sync_playlist(self, playlist_name: str) -> Dict[str, Any]:
        """Sync a single playlist's tracks with Rekordbox.

        Args:
            playlist_name: Name of the playlist directory

        Returns:
            Dictionary with sync results
        """
        logger.info(f"Syncing playlist: {playlist_name}")

        # Parse playlist name for metadata
        metadata = self.name_parser.parse_playlist_name(playlist_name)

        # Handle Event playlists differently
        if self._is_event_playlist(metadata):
            logger.info(f"Processing as event playlist: {playlist_name}")
            return self._sync_event_playlist(playlist_name, metadata)

        # Build the actual tag set with defaults for track playlists
        actual_tags = self._build_actual_tags(metadata)

        logger.info(f"Actual tags for playlist: {actual_tags}")

        # Get MP3 tracks
        mp3_playlist_dir = self.mp3_playlists_root / playlist_name
        mp3_tracks = self._scan_mp3_folder(mp3_playlist_dir)

        # Get Rekordbox tracks matching all actual tags (logical AND)
        rekordbox_tracks = self._get_rekordbox_tracks_with_tags(actual_tags)

        # Compare and sync
        result = self._sync_tracks(mp3_tracks, rekordbox_tracks, actual_tags)

        return {
            "playlist_name": playlist_name,
            "tracks_added": result["added"],
            "tracks_updated": result["updated"],
            "tags_removed": result["removed"],
            "skipped": False,
        }

    def _is_event_playlist(self, metadata: PlaylistMetadata) -> bool:
        """Check if playlist is an event playlist (Party, Set, Radio Moafunk).

        Args:
            metadata: Parsed playlist metadata

        Returns:
            True if this is an event playlist
        """
        # Check if playlist has any event tags
        return bool(
            metadata.party_tags or metadata.set_tags or metadata.radio_moafunk_tags
        )

    def _sync_event_playlist(
        self, playlist_name: str, metadata: PlaylistMetadata
    ) -> Dict[str, Any]:
        """Sync an event playlist with Rekordbox.

        Creates:
        1. Event-specific MyTag (e.g., "Event::Party::23-04-04 carlparty selection")
        2. Intelligent playlist under Events/{event_type}/{event_name}
        3. Tags all tracks with the event tag

        Args:
            playlist_name: Name of the playlist directory
            metadata: Parsed playlist metadata

        Returns:
            Dictionary with sync results
        """
        logger.info(f"Syncing event playlist: {playlist_name}")

        # Determine event type (Party, Set, or Radio Moafunk)
        event_type = self._get_event_type(metadata)
        if not event_type:
            logger.error(f"Could not determine event type for: {playlist_name}")
            return {
                "playlist_name": playlist_name,
                "tracks_added": 0,
                "tracks_updated": 0,
                "tags_removed": 0,
                "skipped": True,
            }

        # Extract clean event name (without emojis)
        event_name = metadata.playlist_name

        # Create event tag in the appropriate category
        # Category: "Party", "Set", or "Radio Moafunk"
        # Tag value: event name (e.g., "23-04-04 carlparty selection")
        logger.info(f"Creating event tag: {event_type}::{event_name}")

        event_tag = self.mytag_manager.create_or_get_tag(event_name, event_type)

        # Get MP3 tracks
        mp3_playlist_dir = self.mp3_playlists_root / playlist_name
        mp3_tracks = self._scan_mp3_folder(mp3_playlist_dir)

        # Track all tracks in this event and tag them
        added_count = 0
        updated_count = 0

        # Build the tag dict for the event
        # Key is the MyTag category (event_type), value is the tag name (event_name)
        event_tags = {event_type: {event_name}}

        for mp3_path in mp3_tracks:
            was_added = self._add_or_update_track(mp3_path, event_tags)
            if was_added:
                added_count += 1
            else:
                updated_count += 1

        # Create intelligent playlist for this event
        self._create_event_intelligent_playlist(event_type, event_name, event_tag)

        self.db.commit()

        return {
            "playlist_name": playlist_name,
            "tracks_added": added_count,
            "tracks_updated": updated_count,
            "tags_removed": 0,
            "skipped": False,
            "event_type": event_type,
            "event_name": event_name,
        }

    def _get_event_type(self, metadata: PlaylistMetadata) -> Optional[str]:
        """Determine the event type from metadata.

        Args:
            metadata: Parsed playlist metadata

        Returns:
            Event type (Party, Set, Radio Moafunk) or None
        """
        # Check which event tag field is populated
        if metadata.party_tags:
            return "Party"
        elif metadata.set_tags:
            return "Set"
        elif metadata.radio_moafunk_tags:
            return "Radio Moafunk"

        return None

    def _create_event_intelligent_playlist(
        self, event_type: str, event_name: str, event_tag: Any
    ) -> None:
        """Create intelligent playlist for an event under Events/{type}/{name}.

        Args:
            event_type: Type of event (Party, Set, Radio Moafunk)
            event_name: Name of the event
            event_tag: MyTag object for this event
        """
        from pyrekordbox.rbxml import (
            LogicalOperator,
            Operator,
            Property,
            SmartList,
        )

        # Get folder structure
        events_folder = self._get_or_create_folder("Events", parent_id=None)

        # Map event type to folder name
        event_folder_map = {
            "Party": "Partys",
            "Set": "Sets",
            "Radio Moafunk": "Radio Moafunk",
        }

        event_folder_name = event_folder_map.get(event_type, event_type)
        type_folder = self._get_or_create_folder(
            event_folder_name, parent_id=events_folder.ID
        )

        # Check if intelligent playlist already exists
        existing_playlist = (
            self.db.query(db6.DjmdPlaylist)
            .filter(
                (db6.DjmdPlaylist.Name == event_name)
                & (db6.DjmdPlaylist.ParentID == type_folder.ID)
                & (db6.DjmdPlaylist.Attribute == 4)
            )
            .first()
        )

        if existing_playlist:
            logger.info(
                f"Intelligent playlist already exists: {event_name} "
                f"under {event_folder_name}"
            )
            return

        # Create smart playlist with Event tag condition
        smart_list = SmartList(logical_operator=LogicalOperator.ALL)
        mytag_id_str = str(event_tag.ID)

        smart_list.add_condition(
            prop=Property.MYTAG,
            operator=Operator.CONTAINS,
            value_left=mytag_id_str,
        )

        # Create the intelligent playlist
        self.db.create_smart_playlist(
            name=event_name,
            smart_list=smart_list,
            parent=type_folder.ID,
        )

        self.db.flush()
        logger.info(
            f"Created intelligent playlist: {event_name} "
            f"under Events/{event_folder_name}"
        )

    def _get_or_create_folder(
        self, folder_name: str, parent_id: Optional[str] = None
    ) -> Any:
        """Get existing folder or create new one.

        Args:
            folder_name: Name of the folder
            parent_id: Parent folder ID (None for root)

        Returns:
            DjmdPlaylist instance with Attribute=1 (folder)
        """
        # Try to find existing folder
        query = self.db.get_playlist(Name=folder_name, Attribute=1)

        if parent_id:
            folder = query.filter(db6.DjmdPlaylist.ParentID == parent_id).first()
        else:
            folder = query.filter(
                (db6.DjmdPlaylist.ParentID == "")
                | (db6.DjmdPlaylist.ParentID.is_(None))
            ).first()

        if folder:
            return folder

        # Create new folder
        logger.info(f"Creating event folder: {folder_name} (parent: {parent_id})")
        folder = self.db.create_playlist(
            name=folder_name,
            parent=parent_id,
            is_folder=True,
        )
        self.db.flush()
        return folder

    def _build_actual_tags(self, metadata: PlaylistMetadata) -> Dict[str, Set[str]]:
        """Build the actual tag set with defaults applied.

        Rules:
        - TrackMetadata::Genre: From parsed genre tags
        - TrackMetadata::Status: Default "Archived" if not specified
        - TrackMetadata::Energy: Optional, only if specified
        - TrackMetadata::Source: Default "Tidal" if not specified
        - EventMetadata: Skip for now

        Args:
            metadata: Parsed playlist metadata

        Returns:
            Dictionary mapping group to set of tag values
        """
        actual_tags: Dict[str, Set[str]] = {
            "Genre": set(),
            "Status": set(),
            "Energy": set(),
            "Source": set(),
        }

        # Genre tags
        if metadata.genre_tags:
            actual_tags["Genre"] = metadata.genre_tags.copy()

        # Status tags (default: Archived)
        if metadata.status_tags:
            actual_tags["Status"] = metadata.status_tags.copy()
        else:
            actual_tags["Status"] = {"Archived"}

        # Energy tags (optional)
        if metadata.energy_tags:
            actual_tags["Energy"] = metadata.energy_tags.copy()

        # Source tags (default: Tidal)
        # Note: Source is not in the current parser, need to add logic
        actual_tags["Source"] = {"Tidal"}

        # Remove empty groups
        actual_tags = {k: v for k, v in actual_tags.items() if v}

        return actual_tags

    def _scan_mp3_folder(self, folder: Path) -> List[Path]:
        """Scan MP3 folder for audio files.

        Args:
            folder: Path to the playlist folder

        Returns:
            List of audio file paths
        """
        if not folder.exists():
            logger.warning(f"MP3 folder does not exist: {folder}")
            return []

        tracks = []
        for file_path in folder.iterdir():
            if (
                file_path.is_file()
                and file_path.suffix.lower() in self.audio_extensions
            ):
                tracks.append(file_path)

        logger.info(f"Found {len(tracks)} audio files in {folder.name}")
        return tracks

    def _get_rekordbox_tracks_with_tags(
        self, actual_tags: Dict[str, Set[str]]
    ) -> List[Any]:
        """Get all Rekordbox tracks that have ALL the specified tags (logical AND).

        Args:
            actual_tags: Dictionary mapping group to set of tag values

        Returns:
            List of DjmdContent instances
        """
        logger.info(f"Querying Rekordbox tracks with tags: {actual_tags}")

        # Use MyTagManager to query tracks with all tags
        tracks = self.mytag_manager.get_content_with_all_tags(actual_tags)

        logger.info(f"Found {len(tracks)} Rekordbox tracks with matching tags")
        return tracks

    def _sync_tracks(
        self,
        mp3_tracks: List[Path],
        rekordbox_tracks: List[Any],
        actual_tags: Dict[str, Set[str]],
    ) -> Dict[str, int]:
        """Sync tracks between MP3 and Rekordbox.

        Logic:
        - Only in MP3: Add track to Rekordbox or add tags if track exists
        - Only in Rekordbox: Remove tags if track has Source::Tidal

        Args:
            mp3_tracks: List of MP3 file paths
            rekordbox_tracks: List of Rekordbox DjmdContent instances
            actual_tags: The tag set to apply/remove

        Returns:
            Dictionary with sync counts
        """
        result = {"added": 0, "updated": 0, "removed": 0}

        # Build identity maps
        mp3_identities = self._build_mp3_identity_map(mp3_tracks)
        rekordbox_identities = self._build_rekordbox_identity_map(rekordbox_tracks)

        # Find differences
        mp3_only = set(mp3_identities.keys()) - set(rekordbox_identities.keys())
        rekordbox_only = set(rekordbox_identities.keys()) - set(mp3_identities.keys())

        logger.info(
            f"Diff: {len(mp3_only)} only in MP3, "
            f"{len(rekordbox_only)} only in Rekordbox"
        )

        # Handle tracks only in MP3
        for identity in mp3_only:
            mp3_path = mp3_identities[identity]
            added = self._add_or_update_track(mp3_path, actual_tags)
            if added:
                result["added"] += 1
            else:
                result["updated"] += 1

        # Handle tracks only in Rekordbox
        for identity in rekordbox_only:
            track = rekordbox_identities[identity]
            removed = self._remove_tags_if_tidal(track, actual_tags)
            if removed:
                result["removed"] += 1

        self.db.flush()

        return result

    def _build_mp3_identity_map(
        self, mp3_tracks: List[Path]
    ) -> Dict[Tuple[str, str], Path]:
        """Build identity map for MP3 tracks.

        Identity is (title, artist) tuple extracted from ID3 metadata.

        Args:
            mp3_tracks: List of MP3 file paths

        Returns:
            Dictionary mapping (title, artist) to file path
        """
        identity_map = {}

        for track_path in mp3_tracks:
            try:
                from mutagen.id3 import ID3

                audio = ID3(str(track_path))
                title = str(audio.get("TIT2", track_path.stem))
                artist_name = str(audio.get("TPE1", "Unknown Artist"))
                identity = (title, artist_name)
                identity_map[identity] = track_path
            except Exception as e:
                logger.warning(f"Could not read metadata from {track_path}: {e}")
                # Fallback to filename-based identity
                identity = (track_path.stem, "Unknown Artist")
                identity_map[identity] = track_path

        return identity_map

    def _build_rekordbox_identity_map(
        self, rekordbox_tracks: List[Any]
    ) -> Dict[Tuple[str, str], Any]:
        """Build identity map for Rekordbox tracks.

        Args:
            rekordbox_tracks: List of DjmdContent instances

        Returns:
            Dictionary mapping (title, artist) to DjmdContent
        """
        identity_map = {}

        for track in rekordbox_tracks:
            artist_name = "Unknown Artist"
            if track.Artist:
                artist_name = track.Artist.Name
            title = track.Title
            identity = (title, artist_name)
            identity_map[identity] = track

        return identity_map

    def _add_or_update_track(
        self, mp3_path: Path, actual_tags: Dict[str, Set[str]]
    ) -> bool:
        """Add track to Rekordbox or update tags if it exists.

        Args:
            mp3_path: Path to the MP3 file
            actual_tags: Tags to apply

        Returns:
            True if track was added, False if only updated
        """
        # Try to find track by exact path first
        track = self.db.get_content(FolderPath=str(mp3_path)).first()

        # If not found by path, try by metadata (title and artist)
        if not track:
            track = self._find_content_by_metadata(mp3_path)

        if track:
            logger.debug(f"Track exists, updating tags: {mp3_path.name}")
            self._apply_tags_to_track(track, actual_tags)
            return False
        else:
            logger.info(f"Adding new track: {mp3_path.name}")
            track = self._add_track_to_database(mp3_path)
            if track:
                self._apply_tags_to_track(track, actual_tags)
                return True
            else:
                logger.error(f"Failed to add track to database: {mp3_path}")
                return False

    def _apply_tags_to_track(
        self, track: Any, actual_tags: Dict[str, Set[str]]
    ) -> None:
        """Apply MyTags to a track.

        Args:
            track: DjmdContent instance
            actual_tags: Tags to apply
        """
        for group, tag_values in actual_tags.items():
            for tag_value in tag_values:
                self.mytag_manager.link_content_to_mytag(
                    content=track,
                    group_name=group,
                    tag_name=tag_value,
                )
                logger.debug(f"Applied tag {group}::{tag_value} to track {track.Title}")

    def _remove_tags_if_tidal(
        self, track: Any, actual_tags: Dict[str, Set[str]]
    ) -> bool:
        """Remove tags from track if it has Source::Tidal tag.

        Args:
            track: DjmdContent instance
            actual_tags: Tags to remove

        Returns:
            True if tags were removed
        """
        # Check if track has Source::Tidal tag
        has_tidal = self.mytag_manager.content_has_mytag(
            content=track,
            group_name="Source",
            tag_name="Tidal",
        )

        if not has_tidal:
            logger.debug(
                f"Track {track.Title} does not have Source::Tidal, "
                "skipping tag removal"
            )
            return False

        # Remove all actual tags
        for group, tag_values in actual_tags.items():
            for tag_value in tag_values:
                self.mytag_manager.unlink_content_from_mytag(
                    content=track,
                    group_name=group,
                    tag_name=tag_value,
                )
                logger.debug(
                    f"Removed tag {group}::{tag_value} from track {track.Title}"
                )

        return True

    def _find_content_by_metadata(self, track_path: Path) -> Optional[Any]:
        """Find content in database by title and artist metadata.

        Args:
            track_path: Path to the track file

        Returns:
            DjmdContent instance or None
        """
        try:
            from mutagen.id3 import ID3

            audio = ID3(str(track_path))
            title = str(audio.get("TIT2", track_path.stem))
            artist_name = str(audio.get("TPE1", "Unknown Artist"))

            artist = self.db.get_artist(Name=artist_name).first()
            if artist:
                content = self.db.get_content(Title=title, ArtistID=artist.ID).first()
                if content:
                    logger.info(
                        f"Found existing track by metadata: {title} - "
                        f"{artist_name} (path: {content.FolderPath})"
                    )
                    return content
        except Exception as e:
            logger.debug(f"Could not find content by metadata for {track_path}: {e}")

        return None

    def _add_track_to_database(self, track_path: Path) -> Optional[Any]:
        """Add track to Rekordbox database with metadata.

        Args:
            track_path: Path to audio file

        Returns:
            DjmdContent instance or None if failed
        """
        try:
            # Extract metadata using mutagen
            from mutagen.id3 import ID3

            audio = ID3(str(track_path))
            title = str(audio.get("TIT2", track_path.stem))
            artist_name = str(audio.get("TPE1", "Unknown Artist"))
            album_name = str(audio.get("TALB", "Unknown Album"))
            year_str = str(audio.get("TDRC", ""))
            release_year = int(year_str[:4]) if year_str else None

        except Exception as e:
            logger.warning(f"Could not read ID3 tags from {track_path}: {e}")
            title = track_path.stem
            artist_name = "Unknown Artist"
            album_name = "Unknown Album"
            release_year = None

        # Create or get Artist
        artist = self.db.get_artist(Name=artist_name).first()
        if artist is None:
            logger.debug(f"Creating artist: {artist_name}")
            artist = self.db.add_artist(name=artist_name)

        # Create or get Album
        album = self.db.get_album(Name=album_name).first()
        if album is None:
            logger.debug(f"Creating album: {album_name}")
            album = self.db.add_album(name=album_name)

        # Add content with metadata
        content = self.db.add_content(
            str(track_path),
            Title=title,
            ArtistID=artist.ID,
            AlbumID=album.ID,
            ReleaseYear=release_year,
        )

        logger.info(f"Added track to database: {title} - {artist_name}")
        return content
