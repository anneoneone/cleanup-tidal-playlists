"""Tidal Snapshot Service for capturing and syncing Tidal state to database."""

import logging
from typing import Any, Dict

from ..services.tidal_service import TidalService
from .service import DatabaseService
from .sync_state import Change, ChangeType, SyncState, SyncStateComparator

logger = logging.getLogger(__name__)


class TidalSnapshotService:
    """Service for capturing Tidal state and syncing to database."""

    def __init__(self, tidal_service: TidalService, db_service: DatabaseService):
        """Initialize Tidal snapshot service.

        Args:
            tidal_service: TidalService instance for API access
            db_service: DatabaseService instance for database operations
        """
        self.tidal_service = tidal_service
        self.db_service = db_service
        self.comparator = SyncStateComparator()

    def capture_tidal_snapshot(self) -> SyncState:
        """Capture current Tidal state and detect changes.

        Returns:
            SyncState with detected changes

        Raises:
            Exception: If Tidal API access fails
        """
        logger.info("Capturing Tidal snapshot...")

        # Get all playlists from Tidal
        tidal_playlists = self.tidal_service.get_playlists()
        logger.info(f"Found {len(tidal_playlists)} playlists in Tidal")

        # Get all playlists from database
        db_playlists = self.db_service.get_all_playlists()
        logger.info(f"Found {len(db_playlists)} playlists in database")

        # Initialize sync state
        sync_state = SyncState(
            tidal_playlists_count=len(tidal_playlists),
            database_playlists_count=len(db_playlists),
        )

        # Compare playlists
        snapshot_playlists = [
            {
                "tidal_id": p.tidal_id,
                "name": p.name,
                "description": p.description,
            }
            for p in tidal_playlists
        ]
        playlist_changes = self.comparator.compare_playlists(
            db_playlists, snapshot_playlists
        )

        for change in playlist_changes:
            sync_state.add_change(change)

        # Track unique tracks across all playlists
        tidal_track_ids = set()

        # Compare tracks for each playlist
        for tidal_playlist in tidal_playlists:
            logger.info(f"Processing playlist: {tidal_playlist.name}")

            # Get playlist from database
            tidal_id = tidal_playlist.tidal_id
            if not tidal_id:
                logger.warning(f"Playlist {tidal_playlist.name} has no tidal_id")
                continue

            db_playlist = self.db_service.get_playlist_by_tidal_id(tidal_id)

            if db_playlist:
                # Get tracks from Tidal
                tidal_tracks = self.tidal_service.get_playlist_tracks(tidal_id)
                logger.info(
                    f"Found {len(tidal_tracks)} tracks in Tidal "
                    f"playlist '{tidal_playlist.name}'"
                )

                # Count unique tracks
                for track in tidal_tracks:
                    tidal_track_ids.add(track.tidal_id)

                # Get tracks from database
                db_tracks = self.db_service.get_playlist_track_associations(
                    db_playlist.id
                )
                logger.info(
                    f"Found {len(db_tracks)} tracks in database "
                    f"playlist '{db_playlist.name}'"
                )

                # Convert Tidal tracks to snapshot format
                snapshot_tracks = [
                    {
                        "tidal_id": t.tidal_id,
                        "title": t.title,
                        "artist": t.artist,
                        "album": t.album,
                        "album_artist": None,
                        "genre": None,
                        "year": t.year,
                        "duration": t.duration,
                        "isrc": None,
                        "position": idx,
                    }
                    for idx, t in enumerate(tidal_tracks)
                ]

                # Compare tracks
                track_changes = self.comparator.compare_playlist_tracks(
                    db_tracks, snapshot_tracks, db_playlist.id
                )

                for change in track_changes:
                    sync_state.add_change(change)

        # Update total track counts
        sync_state.tidal_tracks_count = len(tidal_track_ids)
        db_tracks_count = len(self.db_service.get_all_tracks())
        sync_state.database_tracks_count = db_tracks_count

        logger.info(
            f"Snapshot complete: {len(sync_state.changes)} changes detected, "
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

        # Process playlist changes first
        playlist_changes = self._get_playlist_changes(sync_state)
        applied_counts.update(self._apply_playlist_changes(playlist_changes))

        # Process track changes
        track_changes = self._get_track_changes(sync_state)
        applied_counts.update(self._apply_track_changes(track_changes))

        logger.info(f"Applied changes: {applied_counts}")
        return applied_counts

    def _get_playlist_changes(self, sync_state: SyncState) -> list[Change]:
        """Get playlist-related changes from sync state."""
        return [
            c
            for c in sync_state.changes
            if c.entity_type == "playlist"
            and c.change_type
            in [
                ChangeType.PLAYLIST_ADDED,
                ChangeType.PLAYLIST_REMOVED,
                ChangeType.PLAYLIST_RENAMED,
                ChangeType.PLAYLIST_DESCRIPTION_CHANGED,
            ]
        ]

    def _get_track_changes(self, sync_state: SyncState) -> list[Change]:
        """Get track-related changes from sync state."""
        return [
            c
            for c in sync_state.changes
            if c.entity_type == "track"
            and c.change_type
            in [
                ChangeType.TRACK_ADDED_TO_PLAYLIST,
                ChangeType.TRACK_REMOVED_FROM_PLAYLIST,
                ChangeType.TRACK_MOVED_WITHIN_PLAYLIST,
                ChangeType.TRACK_METADATA_CHANGED,
            ]
        ]

    def _apply_playlist_changes(self, changes: list[Change]) -> Dict[str, int]:
        """Apply playlist changes and return counts."""
        counts: Dict[str, int] = {}

        change_handlers = {
            ChangeType.PLAYLIST_ADDED: self._apply_playlist_added,
            ChangeType.PLAYLIST_REMOVED: self._apply_playlist_removed,
            ChangeType.PLAYLIST_RENAMED: self._apply_playlist_renamed,
            ChangeType.PLAYLIST_DESCRIPTION_CHANGED: self._apply_playlist_description_changed,  # noqa: E501
        }

        for change in changes:
            try:
                handler = change_handlers.get(change.change_type)
                if handler:
                    handler(change)
                    counts[change.change_type.value] = (
                        counts.get(change.change_type.value, 0) + 1
                    )
            except Exception as e:
                logger.error(f"Failed to apply change {change}: {e}")

        return counts

    def _apply_track_changes(self, changes: list[Change]) -> Dict[str, int]:
        """Apply track changes and return counts."""
        counts: Dict[str, int] = {}

        change_handlers = {
            ChangeType.TRACK_ADDED_TO_PLAYLIST: self._apply_track_added_to_playlist,
            ChangeType.TRACK_REMOVED_FROM_PLAYLIST: self._apply_track_removed_from_playlist,  # noqa: E501
            ChangeType.TRACK_MOVED_WITHIN_PLAYLIST: self._apply_track_moved_within_playlist,  # noqa: E501
            ChangeType.TRACK_METADATA_CHANGED: self._apply_track_metadata_changed,
        }

        for change in changes:
            try:
                handler = change_handlers.get(change.change_type)
                if handler:
                    handler(change)
                    counts[change.change_type.value] = (
                        counts.get(change.change_type.value, 0) + 1
                    )
            except Exception as e:
                logger.error(f"Failed to apply change {change}: {e}")

        return counts

    def sync_tidal_to_db(self) -> Dict[str, Any]:
        """Capture Tidal snapshot and apply changes to database.

        Returns:
            Dictionary with sync results including changes detected and applied
        """
        # Capture snapshot
        sync_state = self.capture_tidal_snapshot()

        # Apply changes
        applied_counts = self.apply_tidal_state_to_db(sync_state)

        return {
            "changes_detected": len(sync_state.changes),
            "changes_applied": applied_counts,
            "sync_state": sync_state.to_dict(),
        }

    def _apply_playlist_added(self, change: Change) -> None:
        """Apply PLAYLIST_ADDED change."""
        tidal_id = change.metadata.get("tidal_id")
        if not tidal_id:
            logger.warning(f"No tidal_id in change metadata: {change}")
            return

        # Get playlist from Tidal
        tidal_playlists = self.tidal_service.get_playlists()
        tidal_playlist = next(
            (p for p in tidal_playlists if p.tidal_id == tidal_id), None
        )

        if not tidal_playlist:
            logger.warning(f"Playlist {tidal_id} not found in Tidal")
            return

        # Create playlist in database
        playlist_data = {
            "tidal_id": tidal_playlist.tidal_id,
            "name": tidal_playlist.name,
            "description": tidal_playlist.description,
        }
        self.db_service.create_or_update_playlist(playlist_data)
        logger.info(f"Added playlist: {tidal_playlist.name}")

        # Add tracks to playlist
        tidal_tracks = self.tidal_service.get_playlist_tracks(tidal_id)
        db_playlist = self.db_service.get_playlist_by_tidal_id(tidal_id)

        if db_playlist:
            for idx, tidal_track in enumerate(tidal_tracks):
                track_data = {
                    "tidal_id": tidal_track.tidal_id,
                    "title": tidal_track.title,
                    "artist": tidal_track.artist,
                    "album": tidal_track.album,
                    "year": tidal_track.year,
                    "duration": tidal_track.duration,
                }
                db_track = self.db_service.create_or_update_track(track_data)
                self.db_service.add_track_to_playlist(
                    db_playlist.id, db_track.id, position=idx, in_tidal=True
                )

            logger.info(
                f"Added {len(tidal_tracks)} tracks to playlist {tidal_playlist.name}"
            )

    def _apply_playlist_removed(self, change: Change) -> None:
        """Apply PLAYLIST_REMOVED change (soft delete)."""
        if not change.entity_id:
            logger.warning(f"No entity_id for playlist removal: {change}")
            return

        # Soft delete: mark tracks as not in Tidal
        playlist_tracks = self.db_service.get_playlist_track_associations(
            change.entity_id
        )
        for pt in playlist_tracks:
            self.db_service.update_track_sync_state(
                change.entity_id, pt.track_id, in_tidal=False
            )

        logger.info(f"Marked playlist {change.entity_id} as removed from Tidal")

    def _apply_playlist_renamed(self, change: Change) -> None:
        """Apply PLAYLIST_RENAMED change."""
        if not change.entity_id or not change.new_value:
            logger.warning(f"Missing data for playlist rename: {change}")
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

    def _apply_playlist_description_changed(self, change: Change) -> None:
        """Apply PLAYLIST_DESCRIPTION_CHANGED change."""
        if not change.entity_id:
            logger.warning(f"No entity_id for description change: {change}")
            return

        self.db_service.update_playlist(
            change.entity_id, {"description": change.new_value}
        )
        logger.info(f"Updated description for playlist {change.entity_id}")

    def _apply_track_added_to_playlist(self, change: Change) -> None:
        """Apply TRACK_ADDED_TO_PLAYLIST change."""
        if not change.playlist_id or not change.metadata.get("tidal_id"):
            logger.warning(f"Missing data for track addition: {change}")
            return

        tidal_id = change.metadata["tidal_id"]
        position = change.metadata.get("position", 0)

        # Get track from database or create it
        db_track = self.db_service.get_track_by_tidal_id(tidal_id)

        if not db_track:
            # Need to fetch track from Tidal
            # Get playlist to fetch its tracks
            db_playlist = self.db_service.get_playlist_by_id(change.playlist_id)
            if db_playlist:
                tidal_tracks = self.tidal_service.get_playlist_tracks(
                    db_playlist.tidal_id
                )
                tidal_track = next(
                    (t for t in tidal_tracks if t.tidal_id == tidal_id), None
                )

                if tidal_track:
                    track_data = {
                        "tidal_id": tidal_track.tidal_id,
                        "title": tidal_track.title,
                        "artist": tidal_track.artist,
                        "album": tidal_track.album,
                        "year": tidal_track.year,
                        "duration": tidal_track.duration,
                    }
                    db_track = self.db_service.create_or_update_track(track_data)

        if db_track:
            self.db_service.add_track_to_playlist(
                change.playlist_id, db_track.id, position=position, in_tidal=True
            )
            logger.info(
                f"Added track {tidal_id} to playlist {change.playlist_id} "
                f"at position {position}"
            )

    def _apply_track_removed_from_playlist(self, change: Change) -> None:
        """Apply TRACK_REMOVED_FROM_PLAYLIST change (soft delete)."""
        if not change.playlist_id or not change.track_id:
            logger.warning(f"Missing data for track removal: {change}")
            return

        # Soft delete: mark as not in Tidal
        self.db_service.update_track_sync_state(
            change.playlist_id, change.track_id, in_tidal=False
        )
        logger.info(
            f"Marked track {change.track_id} in playlist {change.playlist_id} "
            f"as removed from Tidal"
        )

    def _apply_track_moved_within_playlist(self, change: Change) -> None:
        """Apply TRACK_MOVED_WITHIN_PLAYLIST change."""
        if not change.playlist_id or not change.track_id or change.new_value is None:
            logger.warning(f"Missing data for track move: {change}")
            return

        self.db_service.update_track_position(
            change.playlist_id, change.track_id, position=int(change.new_value)
        )
        logger.info(
            f"Moved track {change.track_id} in playlist {change.playlist_id} "
            f"to position {change.new_value}"
        )

    def _apply_track_metadata_changed(self, change: Change) -> None:
        """Apply TRACK_METADATA_CHANGED change."""
        if not change.track_id or not change.metadata.get("changes"):
            logger.warning(f"Missing data for metadata change: {change}")
            return

        metadata_changes = change.metadata["changes"]
        update_data = {}

        for field, values in metadata_changes.items():
            update_data[field] = values["new"]

        if update_data:
            self.db_service.update_track(change.track_id, **update_data)
            logger.info(
                f"Updated metadata for track {change.track_id}: "
                f"{list(update_data.keys())}"
            )
