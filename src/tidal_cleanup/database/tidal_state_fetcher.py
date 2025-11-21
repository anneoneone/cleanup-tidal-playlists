"""Service for fetching and updating Tidal state in database.

This service fetches current playlists and tracks from Tidal API and updates
the database to reflect the current state. It's the first step in the unified
sync workflow: Tidal fetch → Filesystem scan → Compare → Sync.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from tidal_cleanup.database.models import (
    DownloadStatus,
    Playlist,
    PlaylistSyncStatus,
    Track,
)
from tidal_cleanup.database.service import DatabaseService

logger = logging.getLogger(__name__)


class TidalStateFetcher:
    """Fetches Tidal playlists and tracks and updates database."""

    def __init__(self, db_service: DatabaseService, tidal_session: Any = None) -> None:
        """Initialize Tidal state fetcher.

        Args:
            db_service: Database service instance
            tidal_session: Authenticated Tidal session (tidalapi.Session)
        """
        self.db_service = db_service
        self.tidal_session = tidal_session
        self._stats: Dict[str, Any] = {}

    def fetch_all_playlists(self, mark_needs_sync: bool = True) -> List[Playlist]:
        """Fetch all user playlists from Tidal and update database.

        Args:
            mark_needs_sync: Whether to mark playlists as needing sync

        Returns:
            List of updated Playlist objects

        Raises:
            RuntimeError: If Tidal session not provided
        """
        if not self.tidal_session:
            raise RuntimeError("Tidal session required to fetch playlists")

        logger.info("Fetching playlists from Tidal...")

        # Get playlists from Tidal
        try:
            tidal_playlists = self.tidal_session.user.playlists()
        except Exception as e:
            logger.error(f"Failed to fetch playlists from Tidal: {e}")
            raise

        logger.info(f"Found {len(tidal_playlists)} playlists in Tidal")

        updated_playlists: List[Playlist] = []
        playlists_created = 0
        playlists_updated = 0
        tracks_created = 0
        tracks_updated = 0

        for tidal_playlist in tidal_playlists:
            try:
                # Convert Tidal playlist to database format
                playlist_data = self._convert_tidal_playlist(tidal_playlist)

                # Check if playlist exists
                existing = self.db_service.get_playlist_by_tidal_id(
                    playlist_data["tidal_id"]
                )

                if existing:
                    # Update existing playlist
                    updated = self._update_playlist(
                        existing, playlist_data, mark_needs_sync
                    )
                    playlists_updated += 1
                else:
                    # Create new playlist
                    updated = self._create_playlist(playlist_data, mark_needs_sync)
                    playlists_created += 1

                updated_playlists.append(updated)

                # Fetch and update tracks for this playlist
                track_count = self._fetch_playlist_tracks(tidal_playlist, updated)
                tracks_created += track_count["created"]
                tracks_updated += track_count["updated"]

            except Exception as e:
                logger.error(f"Error processing playlist '{tidal_playlist.name}': {e}")
                continue

        # Store statistics
        self._stats = {
            "playlists_fetched": len(tidal_playlists),
            "playlists_created": playlists_created,
            "playlists_updated": playlists_updated,
            "tracks_created": tracks_created,
            "tracks_updated": tracks_updated,
        }

        logger.info(
            f"Tidal fetch complete: {playlists_created} playlists created, "
            f"{playlists_updated} updated, {tracks_created} tracks created, "
            f"{tracks_updated} updated"
        )

        return updated_playlists

    def _convert_tidal_playlist(self, tidal_playlist: Any) -> Dict[str, Any]:
        """Convert Tidal playlist object to database format.

        Args:
            tidal_playlist: Tidal API playlist object

        Returns:
            Dictionary with playlist data
        """
        # Extract basic fields
        playlist_data = {
            "tidal_id": tidal_playlist.id,
            "name": tidal_playlist.name,
            "description": getattr(tidal_playlist, "description", None),
        }

        # Extract optional fields
        optional_fields = [
            "creator_name",
            "creator_id",
            "duration",
            "num_tracks",
            "num_videos",
            "popularity",
            "public",
            "picture_url",
            "square_picture_url",
            "share_url",
            "listen_url",
        ]

        for field in optional_fields:
            value = getattr(tidal_playlist, field, None)
            if value is not None:
                playlist_data[field] = value

        # Extract timestamps
        if hasattr(tidal_playlist, "created"):
            playlist_data["created"] = tidal_playlist.created

        if hasattr(tidal_playlist, "last_updated"):
            playlist_data["last_updated"] = tidal_playlist.last_updated
            playlist_data["last_updated_tidal"] = tidal_playlist.last_updated

        if hasattr(tidal_playlist, "last_item_added_at"):
            playlist_data["last_item_added_at"] = tidal_playlist.last_item_added_at

        return playlist_data

    def _create_playlist(
        self, playlist_data: Dict[str, Any], mark_needs_sync: bool
    ) -> Playlist:
        """Create new playlist in database.

        Args:
            playlist_data: Playlist data dictionary
            mark_needs_sync: Whether to mark as needing sync

        Returns:
            Created Playlist object
        """
        # Set sync status
        if mark_needs_sync:
            playlist_data["sync_status"] = PlaylistSyncStatus.NEEDS_DOWNLOAD.value
        else:
            playlist_data["sync_status"] = PlaylistSyncStatus.UNKNOWN.value

        # Set timestamps
        playlist_data["last_seen_in_tidal"] = datetime.utcnow()

        playlist = self.db_service.create_playlist(playlist_data)
        logger.debug(f"Created playlist: {playlist.name} ({playlist.tidal_id})")

        return playlist

    def _update_playlist(
        self,
        existing: Playlist,
        playlist_data: Dict[str, Any],
        mark_needs_sync: bool,
    ) -> Playlist:
        """Update existing playlist in database.

        Args:
            existing: Existing Playlist object
            playlist_data: Updated playlist data
            mark_needs_sync: Whether to mark as needing sync

        Returns:
            Updated Playlist object
        """
        # Check if playlist has changed in Tidal
        tidal_updated = playlist_data.get("last_updated_tidal")
        db_updated = existing.last_updated_tidal

        has_changed = False
        if tidal_updated and db_updated:
            has_changed = tidal_updated > db_updated
        elif tidal_updated and not db_updated:
            has_changed = True

        # Update sync status if changed
        if (
            has_changed
            and mark_needs_sync
            and existing.sync_status == PlaylistSyncStatus.IN_SYNC.value
        ):
            playlist_data["sync_status"] = PlaylistSyncStatus.NEEDS_UPDATE.value
            logger.debug(
                f"Playlist '{existing.name}' changed in Tidal, " "marked for update"
            )

        # Update last seen timestamp
        playlist_data["last_seen_in_tidal"] = datetime.utcnow()

        # Update playlist
        updated = self.db_service.update_playlist(existing.id, playlist_data)
        logger.debug(f"Updated playlist: {updated.name} ({updated.tidal_id})")

        return updated

    def _fetch_playlist_tracks(
        self, tidal_playlist: Any, db_playlist: Playlist
    ) -> Dict[str, int]:
        """Fetch tracks for a playlist and update database.

        Args:
            tidal_playlist: Tidal API playlist object
            db_playlist: Database Playlist object

        Returns:
            Dictionary with 'created' and 'updated' counts
        """
        stats = {"created": 0, "updated": 0}

        try:
            # Get tracks from Tidal
            tidal_tracks = tidal_playlist.tracks()

            # Process each track
            for position, tidal_track in enumerate(tidal_tracks):
                try:
                    # Convert Tidal track to database format
                    track_data = self._convert_tidal_track(tidal_track)

                    # Check if track exists
                    existing = self.db_service.get_track_by_tidal_id(
                        track_data["tidal_id"]
                    )

                    if existing:
                        # Update existing track
                        db_track = self._update_track(existing, track_data)
                        stats["updated"] += 1
                    else:
                        # Create new track
                        db_track = self._create_track(track_data)
                        stats["created"] += 1

                    # Add track to playlist (or update position)
                    self.db_service.add_track_to_playlist(
                        db_playlist.id, db_track.id, position=position
                    )

                except Exception as e:
                    logger.error(
                        f"Error processing track in playlist "
                        f"'{db_playlist.name}': {e}"
                    )
                    continue

        except Exception as e:
            logger.error(
                f"Failed to fetch tracks for playlist '{db_playlist.name}': {e}"
            )

        return stats

    def _convert_tidal_track(self, tidal_track: Any) -> Dict[str, Any]:
        """Convert Tidal track object to database format.

        Args:
            tidal_track: Tidal API track object

        Returns:
            Dictionary with track data
        """
        # Extract basic fields
        track_data = {
            "tidal_id": str(tidal_track.id),
            "title": tidal_track.name,
            "artist": tidal_track.artist.name if tidal_track.artist else "Unknown",
            "album": tidal_track.album.name if tidal_track.album else None,
        }

        # Compute normalized name for matching
        artist_normalized = track_data["artist"].lower().strip()
        title_normalized = track_data["title"].lower().strip()
        track_data["normalized_name"] = f"{artist_normalized} - {title_normalized}"

        # Extract optional data from various sources
        self._extract_optional_track_fields(tidal_track, track_data)
        self._extract_album_metadata(tidal_track, track_data)
        self._extract_audio_quality(tidal_track, track_data)

        return track_data

    def _extract_optional_track_fields(
        self, tidal_track: Any, track_data: Dict[str, Any]
    ) -> None:
        """Extract optional fields from tidal track.

        Args:
            tidal_track: Tidal API track object
            track_data: Dictionary to populate
        """
        if tidal_track.album and hasattr(tidal_track.album, "artist"):
            track_data["album_artist"] = tidal_track.album.artist.name

        # Numeric fields
        optional_numeric = [
            "duration",
            "track_number",
            "volume_number",
            "year",
            "popularity",
        ]
        for field in optional_numeric:
            value = getattr(tidal_track, field, None)
            if value is not None:
                track_data[field] = value

        # Boolean/String fields
        optional_other = ["explicit", "isrc", "copyright", "version"]
        for field in optional_other:
            value = getattr(tidal_track, field, None)
            if value is not None:
                track_data[field] = value

        # Timestamps
        if hasattr(tidal_track, "tidal_release_date"):
            track_data["tidal_release_date"] = tidal_track.tidal_release_date

    def _extract_album_metadata(
        self, tidal_track: Any, track_data: Dict[str, Any]
    ) -> None:
        """Extract album metadata from tidal track.

        Args:
            tidal_track: Tidal API track object
            track_data: Dictionary to populate
        """
        if not tidal_track.album:
            return

        if hasattr(tidal_track.album, "upc"):
            track_data["album_upc"] = tidal_track.album.upc

        if hasattr(tidal_track.album, "release_date"):
            track_data["album_release_date"] = tidal_track.album.release_date

        # Album cover URL (construct from album ID)
        if hasattr(tidal_track.album, "id"):
            track_data["album_cover_url"] = (
                f"https://resources.tidal.com/images/"
                f"{tidal_track.album.id.replace('-', '/')}/640x640.jpg"
            )

    def _extract_audio_quality(
        self, tidal_track: Any, track_data: Dict[str, Any]
    ) -> None:
        """Extract audio quality fields from tidal track.

        Args:
            tidal_track: Tidal API track object
            track_data: Dictionary to populate
        """
        if hasattr(tidal_track, "audio_quality"):
            track_data["audio_quality"] = tidal_track.audio_quality

        if hasattr(tidal_track, "audio_modes"):
            track_data["audio_modes"] = str(tidal_track.audio_modes)

    def _create_track(self, track_data: Dict[str, Any]) -> Track:
        """Create new track in database.

        Args:
            track_data: Track data dictionary

        Returns:
            Created Track object
        """
        # Set download status for new tracks
        track_data["download_status"] = DownloadStatus.NOT_DOWNLOADED.value

        # Set timestamps
        track_data["last_seen_in_tidal"] = datetime.utcnow()

        track = self.db_service.create_track(track_data)
        logger.debug(
            f"Created track: {track.artist} - {track.title} ({track.tidal_id})"
        )

        return track

    def _update_track(self, existing: Track, track_data: Dict[str, Any]) -> Track:
        """Update existing track in database.

        Args:
            existing: Existing Track object
            track_data: Updated track data

        Returns:
            Updated Track object
        """
        # Update last seen timestamp
        track_data["last_seen_in_tidal"] = datetime.utcnow()

        # Don't overwrite download status or file information
        track_data.pop("download_status", None)
        track_data.pop("file_path", None)
        track_data.pop("file_hash", None)
        track_data.pop("downloaded_at", None)

        updated = self.db_service.update_track(existing.id, track_data)
        logger.debug(
            f"Updated track: {updated.artist} - {updated.title} ({updated.tidal_id})"
        )

        return updated

    def mark_removed_playlists(self) -> int:
        """Mark playlists not seen in Tidal as needing removal.

        Playlists that haven't been updated in current fetch are considered
        deleted from Tidal.

        Returns:
            Number of playlists marked for removal
        """
        cutoff_time = datetime.utcnow()
        marked = 0

        with self.db_service.get_session() as session:
            # Get playlists not seen in recent fetch
            playlists = (
                session.query(Playlist)
                .filter(
                    (Playlist.last_seen_in_tidal.is_(None))
                    | (Playlist.last_seen_in_tidal < cutoff_time)
                )
                .all()
            )

            for playlist in playlists:
                if playlist.sync_status != PlaylistSyncStatus.NEEDS_REMOVAL.value:
                    playlist.sync_status = PlaylistSyncStatus.NEEDS_REMOVAL.value
                    marked += 1
                    logger.debug(
                        f"Playlist '{playlist.name}' not in Tidal, "
                        "marked for removal"
                    )

            session.commit()

        logger.info(f"Marked {marked} playlists for removal")
        return marked

    def get_fetch_statistics(self) -> Dict[str, Any]:
        """Get statistics from last fetch operation.

        Returns:
            Dictionary with fetch statistics
        """
        return self._stats.copy()
