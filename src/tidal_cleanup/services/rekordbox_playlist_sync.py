"""Rekordbox playlist synchronization service with MyTag management."""

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


class PlaylistSyncError(Exception):
    """Exception raised when playlist synchronization fails."""

    pass


class RekordboxPlaylistSynchronizer:
    """Synchronizes MP3 playlists with Rekordbox database and manages MyTags."""

    def __init__(
        self,
        db: Any,
        mp3_playlists_root: Path,
        emoji_config_path: Path,
    ) -> None:
        """Initialize playlist synchronizer.

        Args:
            db: Rekordbox6Database instance
            mp3_playlists_root: Root directory containing MP3 playlist folders
            emoji_config_path: Path to emoji-to-MyTag mapping configuration
        """
        if not PYREKORDBOX_AVAILABLE:
            raise RuntimeError("pyrekordbox is not available")

        self.db = db
        self.mp3_playlists_root = mp3_playlists_root
        self.mytag_manager = MyTagManager(db)
        self.name_parser = PlaylistNameParser(emoji_config_path)

        # Supported audio extensions
        self.audio_extensions = {".mp3", ".flac", ".wav", ".aac", ".m4a"}

    def sync_playlist(self, playlist_name: str) -> Dict[str, Any]:
        """Synchronize a playlist from MP3 folder to Rekordbox database.

        Workflow:
        1. Validate MP3 playlist folder exists
        2. Parse playlist name for metadata (emojis -> MyTags)
        3. Get or create Rekordbox playlist
        4. Compare tracks between MP3 folder and Rekordbox playlist
        5. Add missing tracks (to collection and playlist) with MyTags
        6. Remove extra tracks from playlist and remove their MyTags
        7. Delete playlist if empty after sync

        Args:
            playlist_name: Name of the playlist folder in mp3_playlists_root

        Returns:
            Dictionary with sync results

        Raises:
            PlaylistSyncError: If sync fails
        """
        logger.info(f"Starting sync for playlist: {playlist_name}")

        # Step 1: Validate and get MP3 playlist directory
        mp3_playlist_dir = self._validate_mp3_playlist_dir(playlist_name)

        # Step 2: Parse playlist name for metadata
        playlist_metadata = self.name_parser.parse_playlist_name(playlist_name)

        # Step 3: Get MP3 tracks
        mp3_tracks = self._scan_mp3_folder(mp3_playlist_dir)
        logger.info(f"Found {len(mp3_tracks)} tracks in MP3 folder")

        # Step 4: Get or create Rekordbox playlist
        rekordbox_playlist = self._get_or_create_playlist(playlist_name)

        # Step 5: Get current Rekordbox tracks
        rekordbox_tracks = self._get_playlist_tracks(rekordbox_playlist)
        logger.info(f"Found {len(rekordbox_tracks)} tracks in Rekordbox playlist")

        # Step 6: Build track identity mappings and determine changes
        mp3_track_identities, rekordbox_track_identities = (
            self._build_track_identity_maps(mp3_tracks, rekordbox_tracks)
        )
        tracks_to_add, tracks_to_remove = self._compute_track_differences(
            mp3_track_identities, rekordbox_track_identities
        )

        # Step 7: Add missing tracks to playlist
        added_count = self._add_tracks_to_playlist(
            rekordbox_playlist, tracks_to_add, mp3_track_identities, playlist_metadata
        )

        # Step 7b: Update MyTags for ALL tracks in the playlist
        updated_tags_count, validation_errors = self._update_all_track_tags(
            mp3_track_identities, playlist_metadata
        )

        # Step 8: Remove tracks that are in Rekordbox but not in MP3 folder
        removed_count = self._remove_tracks_from_playlist(
            rekordbox_playlist,
            tracks_to_remove,
            rekordbox_track_identities,
            playlist_metadata,
        )

        # Step 9: Commit changes
        self.db.commit()
        logger.info("Changes committed to database")

        # Step 10: Check if playlist is empty and delete if needed
        playlist_deleted = self._cleanup_empty_playlist(
            rekordbox_playlist, playlist_name
        )

        # Return results
        return {
            "playlist_name": playlist_name,
            "mp3_tracks_count": len(mp3_tracks),
            "rekordbox_tracks_before": len(rekordbox_tracks),
            "tracks_added": added_count,
            "tracks_removed": removed_count,
            "playlist_deleted": playlist_deleted,
            "final_track_count": (
                0
                if playlist_deleted
                else len(self._refresh_playlist(rekordbox_playlist).Songs)
            ),
        }

    def _validate_mp3_playlist_dir(self, playlist_name: str) -> Path:
        """Validate MP3 playlist directory exists.

        Args:
            playlist_name: Name of the playlist folder

        Returns:
            Path to the playlist directory

        Raises:
            PlaylistSyncError: If directory doesn't exist
        """
        mp3_playlist_dir = self.mp3_playlists_root / playlist_name
        if not mp3_playlist_dir.exists() or not mp3_playlist_dir.is_dir():
            raise PlaylistSyncError(
                f"MP3 playlist folder does not exist: {mp3_playlist_dir}"
            )
        return mp3_playlist_dir

    def _build_track_identity_maps(
        self, mp3_tracks: List[Path], rekordbox_tracks: List[Dict[str, Any]]
    ) -> Tuple[Dict[Tuple[str, str], str], Dict[Tuple[str, str], Any]]:
        """Build identity mappings for MP3 and Rekordbox tracks.

        Args:
            mp3_tracks: List of MP3 track paths
            rekordbox_tracks: List of Rekordbox track dictionaries

        Returns:
            Tuple of (mp3_track_identities, rekordbox_track_identities)
        """
        # Build MP3 track identities: {(title, artist): path}
        mp3_track_identities = {}
        for track_path in mp3_tracks:
            try:
                from mutagen.id3 import ID3

                audio = ID3(str(track_path))
                title = str(audio.get("TIT2", track_path.stem))
                artist_name = str(audio.get("TPE1", "Unknown Artist"))
                identity = (title, artist_name)
                mp3_track_identities[identity] = str(track_path.resolve())
            except Exception as e:
                logger.warning(f"Could not read metadata from {track_path}: {e}")
                # Fallback to path-based identity
                identity = (track_path.stem, "Unknown Artist")
                mp3_track_identities[identity] = str(track_path.resolve())

        # Build Rekordbox track identities: {(title, artist): content}
        rekordbox_track_identities = {}
        for track in rekordbox_tracks:
            if track["content"]:
                content = track["content"]
                artist_name = "Unknown Artist"
                if content.Artist:
                    artist_name = content.Artist.Name
                identity = (content.Title, artist_name)
                rekordbox_track_identities[identity] = content

        return mp3_track_identities, rekordbox_track_identities

    def _compute_track_differences(
        self,
        mp3_track_identities: Dict[Tuple[str, str], str],
        rekordbox_track_identities: Dict[Tuple[str, str], Any],
    ) -> Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]]]:
        """Compute which tracks need to be added or removed.

        Args:
            mp3_track_identities: MP3 track identity mapping
            rekordbox_track_identities: Rekordbox track identity mapping

        Returns:
            Tuple of (tracks_to_add, tracks_to_remove)
        """
        mp3_identities_set = set(mp3_track_identities.keys())
        rekordbox_identities_set = set(rekordbox_track_identities.keys())

        tracks_to_add = mp3_identities_set - rekordbox_identities_set
        tracks_to_remove = rekordbox_identities_set - mp3_identities_set

        logger.info(f"Tracks to add: {len(tracks_to_add)}")
        logger.info(f"Tracks to remove: {len(tracks_to_remove)}")

        return tracks_to_add, tracks_to_remove

    def _add_tracks_to_playlist(
        self,
        playlist: Any,
        tracks_to_add: Set[Tuple[str, str]],
        mp3_track_identities: Dict[Tuple[str, str], str],
        playlist_metadata: PlaylistMetadata,
    ) -> int:
        """Add multiple tracks to playlist.

        Args:
            playlist: DjmdPlaylist instance
            tracks_to_add: Set of track identities to add
            mp3_track_identities: MP3 track identity mapping
            playlist_metadata: Parsed playlist metadata

        Returns:
            Number of tracks successfully added
        """
        added_count = 0
        for identity in tracks_to_add:
            track_path = mp3_track_identities[identity]
            if self._add_track_to_playlist(
                playlist,
                Path(track_path),
                playlist_metadata,
            ):
                added_count += 1
        return added_count

    def _update_all_track_tags(
        self,
        mp3_track_identities: Dict[Tuple[str, str], str],
        playlist_metadata: PlaylistMetadata,
    ) -> Tuple[int, int]:
        """Update MyTags for all tracks in the playlist.

        Args:
            mp3_track_identities: MP3 track identity mapping
            playlist_metadata: Parsed playlist metadata

        Returns:
            Tuple of (updated_count, validation_errors)
        """
        logger.info("Updating MyTags for all tracks in playlist...")
        updated_tags_count = 0
        validation_errors = 0

        for identity in mp3_track_identities.keys():
            track_path = mp3_track_identities[identity]
            content = self._find_content_by_path_or_metadata(track_path)

            if content:
                old_tags = self.mytag_manager.get_content_tag_names(content)
                self._apply_mytags_to_content(content, playlist_metadata)

                if playlist_metadata.genre_tags:
                    self.mytag_manager.remove_no_genre_tag_if_needed(content)

                # Validate tags
                new_tags = self.mytag_manager.get_content_tag_names(content)
                expected_new_tags = set()
                for _group, tag_names in playlist_metadata.all_tags.items():
                    expected_new_tags.update(tag_names)

                if not expected_new_tags.issubset(new_tags):
                    missing = expected_new_tags - new_tags
                    logger.error(
                        f"Tag validation failed for {content.Title}: "
                        f"Missing tags {missing}"
                    )
                    validation_errors += 1
                else:
                    logger.debug(
                        f"Tags validated for {content.Title}: "
                        f"old={old_tags}, new={new_tags}"
                    )

                updated_tags_count += 1

        logger.info(f"Updated MyTags for {updated_tags_count} tracks")
        if validation_errors > 0:
            logger.warning(f"Tag validation errors: {validation_errors}")

        return updated_tags_count, validation_errors

    def _find_content_by_path_or_metadata(self, track_path: str) -> Optional[Any]:
        """Find content in database by path or metadata.

        Args:
            track_path: Path to the track file

        Returns:
            DjmdContent instance or None
        """
        content = self.db.get_content(FolderPath=track_path).first()

        if not content:
            try:
                from mutagen.id3 import ID3

                audio = ID3(track_path)
                title = str(audio.get("TIT2", Path(track_path).stem))
                artist_name = str(audio.get("TPE1", "Unknown Artist"))

                artist = self.db.get_artist(Name=artist_name).first()
                if artist:
                    content = self.db.get_content(
                        Title=title, ArtistID=artist.ID
                    ).first()
            except Exception as e:
                logger.debug(
                    f"Could not find content by metadata for {track_path}: {e}"
                )

        return content

    def _remove_tracks_from_playlist(
        self,
        playlist: Any,
        tracks_to_remove: Set[Tuple[str, str]],
        rekordbox_track_identities: Dict[Tuple[str, str], Any],
        playlist_metadata: PlaylistMetadata,
    ) -> int:
        """Remove multiple tracks from playlist.

        Args:
            playlist: DjmdPlaylist instance
            tracks_to_remove: Set of track identities to remove
            rekordbox_track_identities: Rekordbox track identity mapping
            playlist_metadata: Parsed playlist metadata

        Returns:
            Number of tracks successfully removed
        """
        removed_count = 0
        for identity in tracks_to_remove:
            content = rekordbox_track_identities[identity]
            if self._remove_track_from_playlist(
                playlist,
                content,
                playlist_metadata,
            ):
                removed_count += 1
        return removed_count

    def _cleanup_empty_playlist(self, playlist: Any, playlist_name: str) -> bool:
        """Delete playlist if empty after sync.

        Args:
            playlist: DjmdPlaylist instance
            playlist_name: Name of the playlist

        Returns:
            True if playlist was deleted, False otherwise
        """
        updated_playlist = self._refresh_playlist(playlist)
        if len(updated_playlist.Songs) == 0:
            logger.info(f"Playlist '{playlist_name}' is empty after sync, deleting...")
            self.db.delete_playlist(updated_playlist)
            self.db.commit()
            logger.info(f"Deleted empty playlist: {playlist_name}")
            return True
        return False

    def _scan_mp3_folder(self, folder: Path) -> List[Path]:
        """Scan folder for audio files.

        Args:
            folder: Folder to scan

        Returns:
            List of audio file paths
        """
        tracks = []
        for file_path in sorted(folder.iterdir()):
            if (
                file_path.is_file()
                and file_path.suffix.lower() in self.audio_extensions
            ):
                tracks.append(file_path)

        return tracks

    def _get_or_create_playlist(self, name: str) -> Any:
        """Get existing playlist or create new one.

        Args:
            name: Playlist name

        Returns:
            DjmdPlaylist instance
        """
        # Try to find existing playlist
        playlist = self.db.get_playlist(Name=name).first()

        if playlist:
            logger.info(f"Found existing playlist: {name}")
            return playlist

        # Create new playlist
        logger.info(f"Creating new playlist: {name}")
        playlist = self.db.create_playlist(name)
        self.db.flush()

        return playlist

    def _get_playlist_tracks(self, playlist: Any) -> List[Dict[str, Any]]:
        """Get all tracks in a playlist.

        Args:
            playlist: DjmdPlaylist instance

        Returns:
            List of track dictionaries with path and content
        """
        tracks = []
        for song in playlist.Songs:
            if song.Content:
                tracks.append(
                    {
                        "path": song.Content.FolderPath,
                        "content": song.Content,
                        "song": song,
                    }
                )

        return tracks

    def _add_track_to_playlist(
        self,
        playlist: Any,
        track_path: Path,
        playlist_metadata: PlaylistMetadata,
    ) -> bool:
        """Add track to playlist with metadata and MyTags.

        Args:
            playlist: DjmdPlaylist instance
            track_path: Path to audio file
            playlist_metadata: Parsed playlist metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Adding track: {track_path.name}")

            # Extract metadata and find or create content
            title, artist_name = self._extract_track_metadata(track_path)
            content = self._get_or_create_content(track_path, title, artist_name)

            if not content:
                logger.error(f"Failed to add track to database: {track_path}")
                return False

            # Add track to playlist if not already present
            self._add_content_to_playlist_if_needed(playlist, content, track_path)

            # Note: MyTags will be applied/updated for all tracks in Step 7b
            return True

        except Exception as e:
            logger.error(f"Failed to add track {track_path}: {e}")
            return False

    def _extract_track_metadata(self, track_path: Path) -> Tuple[str, str]:
        """Extract title and artist from track file.

        Args:
            track_path: Path to audio file

        Returns:
            Tuple of (title, artist_name)
        """
        try:
            from mutagen.id3 import ID3

            audio = ID3(str(track_path))
            title = str(audio.get("TIT2", track_path.stem))
            artist_name = str(audio.get("TPE1", "Unknown Artist"))
        except Exception as e:
            logger.warning(f"Could not read ID3 tags from {track_path}: {e}")
            title = track_path.stem
            artist_name = "Unknown Artist"

        return title, artist_name

    def _get_or_create_content(
        self, track_path: Path, title: str, artist_name: str
    ) -> Optional[Any]:
        """Get existing content or create new one.

        Args:
            track_path: Path to audio file
            title: Track title
            artist_name: Artist name

        Returns:
            DjmdContent instance or None
        """
        # First try by file path
        existing_content = self.db.get_content(FolderPath=str(track_path)).first()

        # If not found by path, try by title and artist
        if not existing_content:
            existing_content = self._find_content_by_metadata(title, artist_name)

        if existing_content:
            logger.debug(f"Track already in database: {existing_content.Title}")
            return existing_content

        # Add track to database with metadata
        logger.debug("Adding new track to database...")
        return self._add_track_to_database(track_path)

    def _find_content_by_metadata(self, title: str, artist_name: str) -> Optional[Any]:
        """Find content in database by title and artist.

        Args:
            title: Track title
            artist_name: Artist name

        Returns:
            DjmdContent instance or None
        """
        artist = self.db.get_artist(Name=artist_name).first()
        if artist:
            content = self.db.get_content(Title=title, ArtistID=artist.ID).first()
            if content:
                logger.info(
                    f"Found existing track by metadata: {title} - "
                    f"{artist_name} (existing path: {content.FolderPath})"
                )
                return content
        return None

    def _add_content_to_playlist_if_needed(
        self, playlist: Any, content: Any, track_path: Path
    ) -> None:
        """Add content to playlist if not already present.

        Args:
            playlist: DjmdPlaylist instance
            content: DjmdContent instance
            track_path: Path to audio file (for logging)
        """
        # Check if track is already in the playlist to avoid duplicates
        # Compare by content ID, not path (same track can have different paths)
        track_in_playlist = any(
            song.Content and song.Content.ID == content.ID for song in playlist.Songs
        )

        if track_in_playlist:
            logger.debug(f"Track already in playlist: {track_path.name}")
        else:
            self.db.add_to_playlist(playlist, content)
            logger.debug(f"Added track to playlist: {track_path.name}")

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

    def _apply_mytags_to_content(
        self,
        content: Any,
        playlist_metadata: PlaylistMetadata,
    ) -> None:
        """Apply MyTags to content based on playlist metadata.

        Args:
            content: DjmdContent instance
            playlist_metadata: Parsed playlist metadata
        """
        # Apply tags for each group
        for group, tag_names in playlist_metadata.all_tags.items():
            for tag_name in tag_names:
                tag = self.mytag_manager.create_or_get_tag(tag_name, group)
                self.mytag_manager.link_content_to_tag(content, tag)

        logger.debug(
            f"Applied MyTags to content {content.ID}: " f"{playlist_metadata.all_tags}"
        )

    def _remove_track_from_playlist(
        self,
        playlist: Any,
        content: Any,
        playlist_metadata: PlaylistMetadata,
    ) -> bool:
        """Remove track from playlist and clean up MyTags.

        Args:
            playlist: DjmdPlaylist instance
            content: DjmdContent instance
            playlist_metadata: Parsed playlist metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get artist name for logging
            artist_name = "Unknown Artist"
            if content.Artist:
                artist_name = content.Artist.Name

            logger.info(f"Removing track: {content.Title} - {artist_name}")

            # Find the song in playlist by content ID
            song = None
            for s in playlist.Songs:
                if s.Content and s.Content.ID == content.ID:
                    song = s
                    break

            if not song:
                logger.warning(
                    f"Track not found in playlist: {content.Title} - {artist_name}"
                )
                return False

            # Remove from playlist ONLY (not from collection)
            self.db.remove_from_playlist(playlist, song)
            logger.info(
                f"Removed track from playlist (kept in collection): "
                f"{content.Title} - {artist_name}"
            )

            # Remove ONLY the MyTags associated with THIS playlist
            self._remove_mytags_from_content(content, playlist_metadata)

            # Check if all Genre tags were removed, add NoGenre if needed
            genre_tags_after = self.mytag_manager.get_content_tags(
                content, group_name="Genre"
            )
            if not genre_tags_after:
                self.mytag_manager.ensure_no_genre_tag(content)

            return True

        except Exception as e:
            logger.error(f"Failed to remove track {content.Title}: {e}")
            return False

    def _remove_mytags_from_content(
        self,
        content: Any,
        playlist_metadata: PlaylistMetadata,
    ) -> None:
        """Remove MyTags from content based on playlist metadata.

        Args:
            content: DjmdContent instance
            playlist_metadata: Parsed playlist metadata
        """
        # Remove tags for each group
        for group, tag_names in playlist_metadata.all_tags.items():
            for tag_name in tag_names:
                # Get the tag
                tag = self.mytag_manager.create_or_get_tag(tag_name, group)
                # Unlink from content
                self.mytag_manager.unlink_content_from_tag(content, tag)

        logger.debug(
            f"Removed MyTags from content {content.ID}: "
            f"{playlist_metadata.all_tags}"
        )

    def _refresh_playlist(self, playlist: Any) -> Any:
        """Refresh playlist data from database.

        Args:
            playlist: DjmdPlaylist instance

        Returns:
            Refreshed playlist instance with updated Songs relationship
        """
        # Query the playlist again to get fresh data with Songs relationship loaded
        refreshed = self.db.get_playlist(Name=playlist.Name).first()
        return refreshed if refreshed else playlist
