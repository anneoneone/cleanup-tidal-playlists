"""Tidal Snapshot Service for capturing and syncing Tidal state to database.

This service provides the main interface for synchronizing Tidal playlists and tracks
with the local database. It detects changes and applies them atomically.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from tidal_cleanup.database.models import Playlist, PlaylistTrack

from ...database.service import DatabaseService
from ..sync.state import Change, ChangeType, SyncState, SyncStateComparator

if TYPE_CHECKING:
    from .api_client import TidalService

logger = logging.getLogger(__name__)


class TidalSnapshotService:
    """Service for capturing Tidal state and syncing to database.

    This service follows a two-phase approach:
    1. Capture: Fetch current Tidal state and compare with database
    2. Apply: Apply detected changes to database with proper locality tracking
    """

    def __init__(self, tidal_service: "TidalService", db_service: DatabaseService):
        """Initialize Tidal snapshot service.

        Args:
            tidal_service: TidalService instance for API access
            db_service: DatabaseService instance for database operations
        """
        self.tidal_service = tidal_service
        self.db_service = db_service
        self.comparator = SyncStateComparator()
        self._playlist_tracks_cache: Dict[str, List[Any]] = {}

    # =========================================================================
    # Public API
    # =========================================================================

    def sync_tidal_to_db(self, playlist_name: Optional[str] = None) -> Dict[str, Any]:
        """Capture Tidal snapshot and apply changes to database.

        Args:
            playlist_name: Optional playlist name to filter sync to specific playlist

        Returns:
            Dictionary with sync results including changes detected and applied
        """
        # Capture snapshot
        sync_state = self.capture_tidal_snapshot(playlist_name=playlist_name)

        # Apply changes
        applied_counts = self.apply_tidal_state_to_db(sync_state)

        return {
            "changes_detected": len(sync_state.changes),
            "changes_applied": applied_counts,
            "sync_state": sync_state.to_dict(),
        }

    def capture_tidal_snapshot(  # noqa: C901
        self, playlist_name: Optional[str] = None
    ) -> SyncState:
        """Capture current Tidal state and detect changes.

        Args:
            playlist_name: Optional playlist name to filter to specific playlist

        Returns:
            SyncState with detected changes

        Raises:
            Exception: If Tidal API access fails
        """
        logger.info("Capturing Tidal snapshot...")

        # Get all playlists from Tidal
        tidal_playlists = self.tidal_service.get_playlists()

        # Filter by playlist name if specified
        if playlist_name:
            tidal_playlists = [p for p in tidal_playlists if p.name == playlist_name]
            if not tidal_playlists:
                logger.warning(f"Playlist '{playlist_name}' not found in Tidal")

        logger.info("Found %d playlists in Tidal", len(tidal_playlists))

        # Get playlists from database (filtered if playlist_name specified)
        if playlist_name:
            with self.db_service.get_session() as session:
                db_playlist = (
                    session.query(Playlist)
                    .filter(Playlist.name == playlist_name)
                    .first()
                )
                db_playlists = [db_playlist] if db_playlist else []
        else:
            db_playlists = self.db_service.get_all_playlists()

        logger.info("Found %d playlists in database", len(db_playlists))

        # Initialize sync state
        sync_state = SyncState(
            tidal_playlists_count=len(tidal_playlists),
            database_playlists_count=len(db_playlists),
        )

        # Compare playlists with all metadata
        snapshot_playlists = [self._playlist_to_dict(p) for p in tidal_playlists]
        playlist_changes = self.comparator.compare_playlists(
            db_playlists, snapshot_playlists
        )

        for change in playlist_changes:
            sync_state.add_change(change)

        # Create empty set to track unique tracks across all playlists
        tidal_track_ids = set()

        # Compare tracks for each playlist
        for tidal_playlist in tidal_playlists:
            logger.info("Processing playlist: %s", tidal_playlist.name)

            # Get playlist from database
            tidal_id = tidal_playlist.tidal_id
            if not tidal_id:
                logger.warning("Playlist %s has no tidal_id", tidal_playlist.name)
                continue

            db_playlist = self.db_service.get_playlist_by_tidal_id(tidal_id)

            if db_playlist:
                # Playlist exists in DB - compare tracks
                tidal_tracks = self.tidal_service.get_playlist_tracks(tidal_id)
                logger.info(
                    f"Found {len(tidal_tracks)} tracks in Tidal "
                    f"playlist '{tidal_playlist.name}'"
                )

                # Count unique tracks
                for track in tidal_tracks:
                    tidal_track_ids.add(track.tidal_id)

                # Get tracks from database
                db_tracks: List[PlaylistTrack] = (
                    self.db_service.get_playlist_track_associations(db_playlist.id)
                )
                logger.info(
                    f"Found {len(db_tracks)} tracks in database "
                    f"playlist '{db_playlist.name}'"
                )

                # Convert Tidal tracks to snapshot format with all metadata
                snapshot_tracks = [
                    self._track_to_snapshot_dict(t, idx)
                    for idx, t in enumerate(tidal_tracks)
                ]

                # Compare tracks
                track_changes = self.comparator.compare_playlist_tracks(
                    db_tracks, snapshot_tracks, db_playlist.id
                )

                for change in track_changes:
                    sync_state.add_change(change)

                # Mark all tracks currently in Tidal as in_tidal=True
                # (regardless of whether changes were detected)
                logger.debug(
                    f"Marking {len(tidal_tracks)} tracks as in_tidal=True "
                    f"for playlist {db_playlist.id}"
                )
                for track in tidal_tracks:
                    if track.tidal_id:
                        db_track = self.db_service.get_track_by_tidal_id(track.tidal_id)
                        if db_track:
                            self.db_service.update_track_sync_state(
                                db_playlist.id, db_track.id, in_tidal=True
                            )
            else:
                # Playlist not in DB yet - will be added via PLAYLIST_ADDED change
                logger.debug(
                    f"Skipping track comparison for new playlist "
                    f"'{tidal_playlist.name}'"
                )

        # Update total track counts
        sync_state.tidal_tracks_count = len(tidal_track_ids)
        db_tracks_count = len(self.db_service.get_all_tracks())
        sync_state.database_tracks_count = db_tracks_count

        logger.info(
            f"Tidal snapshot complete: {len(sync_state.changes)} changes detected, "
            f"{sync_state.tidal_tracks_count} unique Tidal tracks, "
            f"{sync_state.database_tracks_count} database tracks"
        )

        return sync_state

    def apply_tidal_state_to_db(self, sync_state: SyncState) -> Dict[str, int]:
        """Apply Tidal state changes to database.

        Args:
            sync_state: SyncState with detected changes

        Returns:
            Dictionary with counts of applied changes by type
        """
        logger.info("Applying Tidal state to database...")

        applied_counts: Dict[str, int] = {}

        # Process playlist changes first (must be before track changes)
        playlist_changes = self._filter_playlist_changes(sync_state)
        applied_counts.update(self._apply_playlist_changes(playlist_changes))

        # Process track changes
        track_changes = self._filter_track_changes(sync_state)
        applied_counts.update(self._apply_track_changes(track_changes))

        # Clear cache at end of apply phase
        self._playlist_tracks_cache.clear()

        logger.info("Applied changes: %s", applied_counts)
        return applied_counts

    # =========================================================================
    # Change Filtering
    # =========================================================================

    def _filter_playlist_changes(self, sync_state: SyncState) -> list[Change]:
        """Filter playlist-related changes from sync state.

        Returns changes for: ADDED, REMOVED, RENAMED, DESCRIPTION_CHANGED
        """
        playlist_change_types = {
            ChangeType.PLAYLIST_ADDED,
            ChangeType.PLAYLIST_REMOVED,
            ChangeType.PLAYLIST_RENAMED,
            ChangeType.PLAYLIST_DESCRIPTION_CHANGED,
        }

        return [
            change
            for change in sync_state.changes
            if change.entity_type == "playlist"
            and change.change_type in playlist_change_types
        ]

    def _filter_track_changes(self, sync_state: SyncState) -> list[Change]:
        """Filter track-related changes from sync state.

        Returns changes for: ADDED, REMOVED, MOVED, METADATA_CHANGED
        """
        track_change_types = {
            ChangeType.TRACK_ADDED_TO_PLAYLIST,
            ChangeType.TRACK_REMOVED_FROM_PLAYLIST,
            ChangeType.TRACK_MOVED_WITHIN_PLAYLIST,
            ChangeType.TRACK_METADATA_CHANGED,
        }

        return [
            change
            for change in sync_state.changes
            if change.entity_type == "track"
            and change.change_type in track_change_types
        ]

    # =========================================================================
    # Change Application
    # =========================================================================

    def _apply_playlist_changes(self, changes: list[Change]) -> Dict[str, int]:
        """Apply playlist changes to database.

        Processes: ADDED, REMOVED, RENAMED, DESCRIPTION_CHANGED

        Returns:
            Dictionary mapping change type to count of applied changes
        """
        change_handlers = {
            ChangeType.PLAYLIST_ADDED: self._handle_playlist_added,
            ChangeType.PLAYLIST_REMOVED: self._handle_playlist_removed,
            ChangeType.PLAYLIST_RENAMED: self._handle_playlist_renamed,
            ChangeType.PLAYLIST_DESCRIPTION_CHANGED: self._handle_playlist_description_changed,  # noqa: E501
        }

        return self._apply_changes_with_handlers(changes, change_handlers)

    def _apply_track_changes(self, changes: list[Change]) -> Dict[str, int]:
        """Apply track changes to database.

        Processes: ADDED, REMOVED, MOVED, METADATA_CHANGED

        Returns:
            Dictionary mapping change type to count of applied changes
        """
        change_handlers = {
            ChangeType.TRACK_ADDED_TO_PLAYLIST: self._handle_track_added,
            ChangeType.TRACK_REMOVED_FROM_PLAYLIST: self._handle_track_removed,
            ChangeType.TRACK_MOVED_WITHIN_PLAYLIST: self._handle_track_moved,
            ChangeType.TRACK_METADATA_CHANGED: self._handle_track_metadata_changed,
        }

        return self._apply_changes_with_handlers(changes, change_handlers)

    def _apply_changes_with_handlers(
        self, changes: list[Change], handlers: Dict[ChangeType, Any]
    ) -> Dict[str, int]:
        """Apply changes using provided handlers.

        Args:
            changes: List of changes to apply
            handlers: Mapping of change types to handler functions

        Returns:
            Dictionary with counts of successfully applied changes by type
        """
        counts: Dict[str, int] = {}

        for change in changes:
            handler = handlers.get(change.change_type)
            if not handler:
                logger.warning(f"No handler for change type: {change.change_type}")
                continue

            try:
                handler(change)
                change_key = change.change_type.value
                counts[change_key] = counts.get(change_key, 0) + 1
            except Exception as e:
                logger.error(
                    f"Failed to apply {change.change_type}: {e}", exc_info=True
                )

        return counts

    # =========================================================================
    # Playlist Change Handlers
    # =========================================================================

    def _handle_playlist_added(self, change: Change) -> None:
        """Apply PLAYLIST_ADDED change."""
        tidal_id = change.metadata.get("tidal_id")
        playlist_data = change.metadata.get("playlist_data")

        if not tidal_id or not playlist_data:
            logger.warning(
                "Missing tidal_id or playlist_data in change metadata: %s", change
            )
            return

        # Create playlist in database with metadata from change
        logger.debug(
            f"Creating playlist in DB: {playlist_data['name']} "
            f"(tidal_id={tidal_id})"
        )
        self.db_service.create_or_update_playlist(playlist_data)
        logger.info("Added playlist: %s", playlist_data["name"])

        # Fetch tracks from Tidal API with caching
        logger.debug(f"Fetching {tidal_id} tracks from Tidal")
        tidal_tracks = self._get_playlist_tracks_cached(tidal_id)
        logger.debug(f"Retrieved {len(tidal_tracks)} tracks from Tidal")

        db_playlist = self.db_service.get_playlist_by_tidal_id(tidal_id)

        if db_playlist:
            logger.debug(
                f"Adding {len(tidal_tracks)} tracks to playlist {db_playlist.id}"
            )
            for idx, tidal_track in enumerate(tidal_tracks):
                track_data = self._track_to_dict(tidal_track)
                db_track = self.db_service.create_or_update_track(track_data)
                logger.debug(
                    f"  Track {idx}: {track_data['artist']} - {track_data['title']} "
                    f"(tidal_id={track_data['tidal_id']}, db_id={db_track.id})"
                )
                self.db_service.add_track_to_playlist(
                    db_playlist.id, db_track.id, position=idx, in_tidal=True
                )
                logger.debug("    Set in_tidal=True for playlist_track")

            logger.info(
                f"Added {len(tidal_tracks)} tracks to playlist {playlist_data['name']}"
            )

    def _handle_playlist_removed(self, change: Change) -> None:
        """Apply PLAYLIST_REMOVED change (soft delete)."""
        if not change.entity_id:
            logger.warning("No entity_id for playlist removal: %s", change)
            return

        # Soft delete: mark tracks as not in Tidal
        playlist_tracks = self.db_service.get_playlist_track_associations(
            change.entity_id
        )
        for pt in playlist_tracks:
            self.db_service.update_track_sync_state(
                change.entity_id, pt.track_id, in_tidal=False
            )

        logger.info("Marked playlist %d as removed from Tidal", change.entity_id)

    def _handle_playlist_renamed(self, change: Change) -> None:
        """Apply PLAYLIST_RENAMED change."""
        if not change.entity_id or not change.new_value:
            logger.warning("Missing data for playlist rename: %s", change)
            return

        playlist = self.db_service.get_playlist_by_id(change.entity_id)
        if playlist:
            self.db_service.update_playlist(
                change.entity_id, {"name": change.new_value}
            )
            logger.info(
                f"Renamed playlist {change.entity_id}: "
                f"{change.old_value} -> {change.new_value}"
            )

    def _handle_playlist_description_changed(self, change: Change) -> None:
        """Apply PLAYLIST_DESCRIPTION_CHANGED change."""
        if not change.entity_id:
            logger.warning("No entity_id for description change: %s", change)
            return

        self.db_service.update_playlist(
            change.entity_id, {"description": change.new_value}
        )
        logger.info("Updated description for playlist %d", change.entity_id)

    # =========================================================================
    # Track Change Handlers
    # =========================================================================

    def _handle_track_added(self, change: Change) -> None:
        """Apply TRACK_ADDED_TO_PLAYLIST change."""
        if not change.playlist_id or not change.metadata.get("tidal_id"):
            logger.warning("Missing data for track addition: %s", change)
            return

        tidal_id = change.metadata["tidal_id"]
        position = change.metadata.get("position", 0)

        logger.debug(
            f"Handling TRACK_ADDED: tidal_id={tidal_id}, "
            f"playlist_id={change.playlist_id}, position={position}"
        )

        # Get track from database or create it
        db_track = self.db_service.get_track_by_tidal_id(tidal_id)

        if not db_track:
            # Need to fetch track from Tidal
            # Get playlist to fetch its tracks (with caching)
            db_playlist = self.db_service.get_playlist_by_id(change.playlist_id)
            if db_playlist:
                tidal_tracks = self._get_playlist_tracks_cached(db_playlist.tidal_id)
                tidal_track = next(
                    (t for t in tidal_tracks if t.tidal_id == tidal_id), None
                )

                if tidal_track:
                    track_data = self._track_to_dict(tidal_track)
                    db_track = self.db_service.create_or_update_track(track_data)

        if db_track:
            logger.debug(f"Adding track {db_track.id} to playlist {change.playlist_id}")
            self.db_service.add_track_to_playlist(
                change.playlist_id, db_track.id, position=position, in_tidal=True
            )
            logger.debug(
                f"Set in_tidal=True for track {db_track.id} "
                f"in playlist {change.playlist_id}"
            )
            logger.info(
                f"Added track {tidal_id} to playlist {change.playlist_id} "
                f"at position {position}"
            )

    def _handle_track_removed(self, change: Change) -> None:
        """Apply TRACK_REMOVED_FROM_PLAYLIST change (soft delete)."""
        if not change.playlist_id or not change.track_id:
            logger.warning("Missing data for track removal: %s", change)
            return

        logger.debug(
            f"Handling TRACK_REMOVED: track_id={change.track_id}, "
            f"playlist_id={change.playlist_id}"
        )

        # Soft delete: mark as not in Tidal
        self.db_service.update_track_sync_state(
            change.playlist_id, change.track_id, in_tidal=False
        )
        logger.debug(
            f"Set in_tidal=False for track {change.track_id} "
            f"in playlist {change.playlist_id}"
        )
        logger.info(
            f"Marked track {change.track_id} in playlist {change.playlist_id} "
            f"as removed from Tidal"
        )

    def _handle_track_moved(self, change: Change) -> None:
        """Apply TRACK_MOVED_WITHIN_PLAYLIST change."""
        if not change.playlist_id or not change.track_id or change.new_value is None:
            logger.warning("Missing data for track move: %s", change)
            return

        logger.debug(
            f"Handling TRACK_MOVED: track_id={change.track_id}, "
            f"playlist_id={change.playlist_id}, "
            f"old_position={change.old_value}, new_position={change.new_value}"
        )

        self.db_service.update_track_position(
            change.playlist_id, change.track_id, position=int(change.new_value)
        )
        logger.info(
            f"Moved track {change.track_id} in playlist {change.playlist_id} "
            f"to position {change.new_value}"
        )

    def _handle_track_metadata_changed(self, change: Change) -> None:
        """Apply TRACK_METADATA_CHANGED change."""
        if not change.track_id or not change.metadata.get("changes"):
            logger.warning("Missing data for metadata change: %s", change)
            return

        metadata_changes = change.metadata["changes"]
        update_data = {}

        for field, values in metadata_changes.items():
            update_data[field] = values["new"]

        if update_data:
            self.db_service.update_track(change.track_id, update_data)
            logger.info(
                f"Updated metadata for track {change.track_id}: "
                f"{list(update_data.keys())}"
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_playlist_tracks_cached(self, tidal_id: str) -> List[Any]:
        """Get playlist tracks with caching to avoid redundant API calls.

        Args:
            tidal_id: Tidal playlist ID

        Returns:
            List of track objects from Tidal API (empty list if fetch fails)
        """
        if tidal_id not in self._playlist_tracks_cache:
            try:
                tracks = self.tidal_service.get_playlist_tracks(tidal_id)
                # Ensure we always store a list, even if API returns None
                self._playlist_tracks_cache[tidal_id] = tracks if tracks else []
            except Exception as e:
                logger.error(
                    f"Failed to fetch tracks for playlist {tidal_id}: {e}",
                    exc_info=True,
                )
                # Cache empty list to avoid repeated failed API calls
                self._playlist_tracks_cache[tidal_id] = []

        return self._playlist_tracks_cache[tidal_id]

    # =========================================================================
    # Data Conversion Helpers
    # =========================================================================

    def _playlist_to_dict(self, playlist: Any) -> Dict[str, Any]:
        """Convert Tidal playlist to dictionary with all metadata.

        Args:
            playlist: Tidal playlist object

        Returns:
            Dictionary with all playlist metadata fields
        """
        return {
            "tidal_id": playlist.tidal_id,
            "name": playlist.name,
            "description": playlist.description,
            "creator_name": getattr(playlist, "creator_name", None),
            "creator_id": getattr(playlist, "creator_id", None),
            "duration": getattr(playlist, "duration", None),
            "num_tracks": getattr(playlist, "num_tracks", None),
            "num_videos": getattr(playlist, "num_videos", None),
            "popularity": getattr(playlist, "popularity", None),
            "public": getattr(playlist, "public", None),
            "picture_url": getattr(playlist, "picture_url", None),
            "square_picture_url": getattr(playlist, "square_picture_url", None),
            "created": getattr(playlist, "created", None),
            "last_updated": getattr(playlist, "last_updated", None),
            "last_item_added_at": getattr(playlist, "last_item_added_at", None),
            "share_url": getattr(playlist, "share_url", None),
            "listen_url": getattr(playlist, "listen_url", None),
        }

    def _track_to_dict(self, track: Any) -> Dict[str, Any]:
        """Convert Tidal track to dictionary with all metadata.

        Args:
            track: Tidal track object

        Returns:
            Dictionary with all track metadata fields
        """
        return {
            "tidal_id": track.tidal_id,
            "title": track.title,
            "artist": track.artist,
            "album": getattr(track, "album", None),
            "album_artist": getattr(track, "album_artist", None),
            "year": getattr(track, "year", None),
            "duration": getattr(track, "duration", None),
            "track_number": getattr(track, "track_number", None),
            "volume_number": getattr(track, "volume_number", None),
            "explicit": getattr(track, "explicit", None),
            "popularity": getattr(track, "popularity", None),
            "copyright": getattr(track, "copyright", None),
            "tidal_release_date": getattr(track, "tidal_release_date", None),
            "audio_quality": getattr(track, "audio_quality", None),
            "audio_modes": getattr(track, "audio_modes", None),
            "version": getattr(track, "version", None),
            "isrc": getattr(track, "isrc", None),
            "album_upc": getattr(track, "album_upc", None),
            "album_release_date": getattr(track, "album_release_date", None),
            "album_cover_url": getattr(track, "album_cover_url", None),
        }

    def _track_to_snapshot_dict(self, track: Any, position: int) -> Dict[str, Any]:
        """Convert Tidal track to snapshot dictionary format.

        Args:
            track: Tidal track object
            position: Track position in playlist

        Returns:
            Dictionary with track metadata for snapshot comparison
        """
        track_dict = self._track_to_dict(track)
        track_dict["position"] = position
        return track_dict
