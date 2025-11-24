"""Database service for managing playlist and track synchronization."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from .models import Base, Playlist, PlaylistTrack, SyncOperation, SyncSnapshot, Track

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for database operations and transaction management."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize database service.

        Args:
            db_path: Path to SQLite database file.
                    If None, uses default ~/.tidal-cleanup/sync.db
        """
        if db_path is None:
            db_path = Path.home() / ".tidal-cleanup" / "sync.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create engine
        db_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(db_url, echo=False)

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

        logger.info("Database initialized at: %s", self.db_path)

    def init_db(self) -> None:
        """Initialize database schema (create all tables)."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database schema created successfully")

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy Session object

        Note:
            Caller is responsible for closing the session
        """
        return self.SessionLocal()

    # =========================================================================
    # Track Operations
    # =========================================================================

    def get_track_by_id(self, track_id: int) -> Optional[Track]:
        """Get track by database ID.

        Args:
            track_id: Track database ID

        Returns:
            Track object or None if not found
        """
        with self.get_session() as session:
            return session.get(Track, track_id)

    def get_track_by_tidal_id(self, tidal_id: str) -> Optional[Track]:
        """Get track by Tidal ID.

        Args:
            tidal_id: Tidal track ID

        Returns:
            Track object or None if not found
        """
        with self.get_session() as session:
            stmt = select(Track).where(Track.tidal_id == tidal_id)
            return session.scalar(stmt)

    def get_track_by_path(self, file_path: str) -> Optional[Track]:
        """Get track by file path.

        Args:
            file_path: File path (relative to MP3 directory)

        Returns:
            Track object or None if not found
        """
        with self.get_session() as session:
            stmt = select(Track).where(Track.file_path == file_path)
            return session.scalar(stmt)

    def find_track_by_metadata(self, title: str, artist: str) -> Optional[Track]:
        """Find track by metadata (title and artist).

        Args:
            title: Track title
            artist: Track artist

        Returns:
            Track object or None if not found
        """
        with self.get_session() as session:
            stmt = select(Track).where(Track.title == title, Track.artist == artist)
            return session.scalar(stmt)

    def find_track_by_normalized_name(self, normalized_name: str) -> Optional[Track]:
        """Find track by normalized name.

        Args:
            normalized_name: Normalized track name

        Returns:
            Track object or None if not found
        """
        with self.get_session() as session:
            stmt = select(Track).where(Track.normalized_name == normalized_name)
            return session.scalar(stmt)

    def create_track(self, track_data: Dict[str, Any]) -> Track:
        """Create a new track.

        Args:
            track_data: Track data dictionary

        Returns:
            Created Track object
        """
        with self.get_session() as session:
            # Compute normalized name if not provided
            if "normalized_name" not in track_data:
                track_data["normalized_name"] = self._normalize_track_name(
                    track_data.get("title", ""), track_data.get("artist", "")
                )

            track = Track(**track_data)
            session.add(track)
            session.commit()
            session.refresh(track)
            logger.info(
                f"Created track: {track.artist} - {track.title} (ID: {track.id})"
            )
            return track

    def update_track(self, track_id: int, track_data: Dict[str, Any]) -> Track:
        """Update an existing track.

        Args:
            track_id: Track database ID
            track_data: Track data dictionary with fields to update

        Returns:
            Updated Track object
        """
        with self.get_session() as session:
            track = session.get(Track, track_id)
            if not track:
                raise ValueError(f"Track not found: {track_id}")

            # Update fields
            for key, value in track_data.items():
                if hasattr(track, key):
                    setattr(track, key, value)

            track.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(track)
            logger.debug("Updated track: %s", track.id)
            return track

    def create_or_update_track(self, track_data: Dict[str, Any]) -> Track:
        """Create track if it doesn't exist, otherwise update it.

        Args:
            track_data: Track data dictionary

        Returns:
            Track object
        """
        # Try to find existing track by tidal_id
        tidal_id = track_data.get("tidal_id")
        if tidal_id:
            existing_track = self.get_track_by_tidal_id(tidal_id)
            if existing_track:
                return self.update_track(existing_track.id, track_data)

        # Try to find by file path
        file_path = track_data.get("file_path")
        if file_path:
            existing_track = self.get_track_by_path(file_path)
            if existing_track:
                return self.update_track(existing_track.id, track_data)

        # Try to find by metadata
        title = track_data.get("title")
        artist = track_data.get("artist")
        if title and artist:
            existing_track = self.find_track_by_metadata(title, artist)
            if existing_track:
                return self.update_track(existing_track.id, track_data)

        # Create new track
        return self.create_track(track_data)

    def get_all_tracks(self) -> List[Track]:
        """Get all tracks from database.

        Returns:
            List of Track objects
        """
        with self.get_session() as session:
            stmt = select(Track)
            return list(session.scalars(stmt).all())

    # =========================================================================
    # Playlist Operations
    # =========================================================================

    def get_playlist_by_id(self, playlist_id: int) -> Optional[Playlist]:
        """Get playlist by database ID.

        Args:
            playlist_id: Playlist database ID

        Returns:
            Playlist object or None if not found
        """
        with self.get_session() as session:
            return session.get(Playlist, playlist_id)

    def get_playlist_by_tidal_id(self, tidal_id: str) -> Optional[Playlist]:
        """Get playlist by Tidal ID.

        Args:
            tidal_id: Tidal playlist ID

        Returns:
            Playlist object or None if not found
        """
        with self.get_session() as session:
            stmt = select(Playlist).where(Playlist.tidal_id == tidal_id)
            return session.scalar(stmt)

    def get_playlist_by_name(self, name: str) -> Optional[Playlist]:
        """Get playlist by name.

        Args:
            name: Playlist name

        Returns:
            Playlist object or None if not found
        """
        with self.get_session() as session:
            stmt = select(Playlist).where(Playlist.name == name)
            return session.scalar(stmt)

    def get_all_playlists(self) -> List[Playlist]:
        """Get all playlists from database.

        Returns:
            List of Playlist objects
        """
        with self.get_session() as session:
            stmt = select(Playlist)
            return list(session.scalars(stmt).all())

    def create_playlist(self, playlist_data: Dict[str, Any]) -> Playlist:
        """Create a new playlist.

        Args:
            playlist_data: Playlist data dictionary

        Returns:
            Created Playlist object
        """
        with self.get_session() as session:
            playlist = Playlist(**playlist_data)
            session.add(playlist)
            session.commit()
            session.refresh(playlist)
            logger.info("Created playlist: %s (ID: %s)", playlist.name, playlist.id)
            return playlist

    def update_playlist(
        self, playlist_id: int, playlist_data: Dict[str, Any]
    ) -> Playlist:
        """Update an existing playlist.

        Args:
            playlist_id: Playlist database ID
            playlist_data: Playlist data dictionary with fields to update

        Returns:
            Updated Playlist object
        """
        with self.get_session() as session:
            playlist = session.get(Playlist, playlist_id)
            if not playlist:
                raise ValueError(f"Playlist not found: {playlist_id}")

            # Update fields
            for key, value in playlist_data.items():
                if hasattr(playlist, key):
                    setattr(playlist, key, value)

            playlist.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(playlist)
            logger.debug("Updated playlist: %s", playlist.id)
            return playlist

    def create_or_update_playlist(self, playlist_data: Dict[str, Any]) -> Playlist:
        """Create playlist if it doesn't exist, otherwise update it.

        Args:
            playlist_data: Playlist data dictionary

        Returns:
            Playlist object
        """
        # Try to find existing playlist by tidal_id
        tidal_id = playlist_data.get("tidal_id")
        if tidal_id:
            existing_playlist = self.get_playlist_by_tidal_id(tidal_id)
            if existing_playlist:
                return self.update_playlist(existing_playlist.id, playlist_data)

        # Create new playlist
        return self.create_playlist(playlist_data)

    # =========================================================================
    # Playlist-Track Relationship Operations
    # =========================================================================

    def add_track_to_playlist(
        self,
        playlist_id: int,
        track_id: int,
        position: Optional[int] = None,
        in_tidal: bool = False,
        in_local: bool = False,
        in_rekordbox: bool = False,
    ) -> PlaylistTrack:
        """Add track to playlist (or update if already exists).

        Args:
            playlist_id: Playlist database ID
            track_id: Track database ID
            position: Track position in playlist
            in_tidal: Whether track is in Tidal
            in_local: Whether track is downloaded locally
            in_rekordbox: Whether track is in Rekordbox

        Returns:
            PlaylistTrack object
        """
        with self.get_session() as session:
            # Check if relationship already exists
            stmt = select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id,
            )
            playlist_track = session.scalar(stmt)

            if playlist_track:
                # Update existing relationship
                if position is not None:
                    playlist_track.position = position
                if in_tidal:
                    playlist_track.in_tidal = True
                    if not playlist_track.added_to_tidal:
                        playlist_track.added_to_tidal = datetime.now(timezone.utc)
                if in_local:
                    playlist_track.in_local = True
                    if not playlist_track.added_to_local:
                        playlist_track.added_to_local = datetime.now(timezone.utc)
                if in_rekordbox:
                    playlist_track.in_rekordbox = True
                    if not playlist_track.added_to_rekordbox:
                        playlist_track.added_to_rekordbox = datetime.now(timezone.utc)
                playlist_track.updated_at = datetime.now(timezone.utc)
            else:
                # Create new relationship
                now = datetime.now(timezone.utc)
                playlist_track = PlaylistTrack(
                    playlist_id=playlist_id,
                    track_id=track_id,
                    position=position,
                    in_tidal=in_tidal,
                    in_local=in_local,
                    in_rekordbox=in_rekordbox,
                    added_to_tidal=now if in_tidal else None,
                    added_to_local=now if in_local else None,
                    added_to_rekordbox=now if in_rekordbox else None,
                )
                session.add(playlist_track)

            session.commit()
            session.refresh(playlist_track)
            return playlist_track

    def remove_track_from_playlist(
        self, playlist_id: int, track_id: int, source: str = "tidal"
    ) -> bool:
        """Remove track from playlist (mark as removed from source).

        Args:
            playlist_id: Playlist database ID
            track_id: Track database ID
            source: Source to mark as removed from ('tidal', 'local', 'rekordbox')

        Returns:
            True if relationship was updated, False if not found
        """
        with self.get_session() as session:
            stmt = select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id,
            )
            playlist_track = session.scalar(stmt)

            if not playlist_track:
                return False

            # Mark as removed from specified source
            if source == "tidal":
                playlist_track.in_tidal = False
                playlist_track.removed_from_tidal = datetime.now(timezone.utc)
            elif source == "local":
                playlist_track.in_local = False
            elif source == "rekordbox":
                playlist_track.in_rekordbox = False

            playlist_track.updated_at = datetime.now(timezone.utc)

            # If track is not in any source, delete the relationship
            if (
                not playlist_track.in_tidal
                and not playlist_track.in_local
                and not playlist_track.in_rekordbox
            ):
                session.delete(playlist_track)
                logger.debug(
                    f"Deleted playlist_track: "
                    f"playlist={playlist_id}, track={track_id}"
                )

            session.commit()
            return True

    def get_playlist_tracks(self, playlist_id: int) -> List[Track]:
        """Get all tracks in a playlist.

        Args:
            playlist_id: Playlist database ID

        Returns:
            List of Track objects
        """
        with self.get_session() as session:
            playlist = session.get(Playlist, playlist_id)
            if not playlist:
                return []

            # Get tracks through relationship, ordered by position
            stmt = (
                select(Track)
                .join(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position)
            )
            return list(session.scalars(stmt).all())

    def get_playlist_track_associations(self, playlist_id: int) -> List[PlaylistTrack]:
        """Get all PlaylistTrack associations for a playlist.

        This method returns PlaylistTrack objects with their relationships loaded,
        which is useful for accessing both track data and playlist-specific info
        like position.

        Args:
            playlist_id: Playlist database ID

        Returns:
            List of PlaylistTrack objects with track relationship loaded
        """
        with self.get_session() as session:
            stmt = (
                select(PlaylistTrack)
                .options(joinedload(PlaylistTrack.track))
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position)
            )
            return list(session.scalars(stmt).all())

    def get_track_playlists(self, track_id: int) -> List[Playlist]:
        """Get all playlists containing a track.

        Args:
            track_id: Track database ID

        Returns:
            List of Playlist objects
        """
        with self.get_session() as session:
            track = session.get(Track, track_id)
            if not track:
                return []

            # Get playlists through relationship
            stmt = (
                select(Playlist)
                .join(PlaylistTrack)
                .where(PlaylistTrack.track_id == track_id)
            )
            return list(session.scalars(stmt).all())

    def update_track_position(
        self, playlist_id: int, track_id: int, position: int
    ) -> bool:
        """Update track position in a playlist.

        Args:
            playlist_id: Playlist database ID
            track_id: Track database ID
            position: New position (0-indexed)

        Returns:
            True if updated, False if not found
        """
        with self.get_session() as session:
            stmt = select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id,
            )
            playlist_track = session.scalar(stmt)

            if not playlist_track:
                logger.warning(
                    f"PlaylistTrack not found: "
                    f"playlist={playlist_id}, track={track_id}"
                )
                return False

            playlist_track.position = position
            session.commit()
            logger.debug(
                f"Updated track position: playlist={playlist_id}, "
                f"track={track_id}, position={position}"
            )
            return True

    def update_track_sync_state(
        self,
        playlist_id: int,
        track_id: int,
        in_tidal: Optional[bool] = None,
        in_local: Optional[bool] = None,
        in_rekordbox: Optional[bool] = None,
    ) -> bool:
        """Update sync state flags for a track in a playlist.

        Args:
            playlist_id: Playlist database ID
            track_id: Track database ID
            in_tidal: Whether track is in Tidal (None = no change)
            in_local: Whether track is in local files (None = no change)
            in_rekordbox: Whether track is in Rekordbox (None = no change)

        Returns:
            True if updated, False if not found
        """
        with self.get_session() as session:
            stmt = select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id,
            )
            playlist_track = session.scalar(stmt)

            if not playlist_track:
                logger.warning(
                    f"PlaylistTrack not found: "
                    f"playlist={playlist_id}, track={track_id}"
                )
                return False

            if in_tidal is not None:
                playlist_track.in_tidal = in_tidal
            if in_local is not None:
                playlist_track.in_local = in_local
            if in_rekordbox is not None:
                playlist_track.in_rekordbox = in_rekordbox

            session.commit()
            logger.debug(
                f"Updated track sync state: playlist={playlist_id}, "
                f"track={track_id}"
            )
            return True

    # =========================================================================
    # Sync Operation Management
    # =========================================================================

    def create_sync_operation(self, operation_data: Dict[str, Any]) -> SyncOperation:
        """Create a sync operation record.

        Args:
            operation_data: Operation data dictionary

        Returns:
            Created SyncOperation object
        """
        with self.get_session() as session:
            operation = SyncOperation(**operation_data)
            session.add(operation)
            session.commit()
            session.refresh(operation)
            logger.debug(
                f"Created sync operation: {operation.operation_type} "
                f"(ID: {operation.id})"
            )
            return operation

    def get_pending_operations(self) -> List[SyncOperation]:
        """Get all pending sync operations.

        Returns:
            List of SyncOperation objects with status='pending'
        """
        with self.get_session() as session:
            stmt = select(SyncOperation).where(SyncOperation.status == "pending")
            return list(session.scalars(stmt).all())

    def update_operation_status(
        self,
        operation_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> SyncOperation:
        """Update sync operation status.

        Args:
            operation_id: Operation database ID
            status: New status ('running', 'completed', 'failed')
            error_message: Optional error message for failed operations

        Returns:
            Updated SyncOperation object
        """
        with self.get_session() as session:
            operation = session.get(SyncOperation, operation_id)
            if not operation:
                raise ValueError(f"Operation not found: {operation_id}")

            operation.status = status
            if error_message:
                operation.error_message = error_message

            if status == "running" and not operation.started_at:
                operation.started_at = datetime.now(timezone.utc)
            elif status in ("completed", "failed"):
                operation.completed_at = datetime.now(timezone.utc)

            session.commit()
            session.refresh(operation)
            return operation

    # =========================================================================
    # Snapshot Management
    # =========================================================================

    def create_snapshot(self, snapshot_type: str, data: Dict[str, Any]) -> SyncSnapshot:
        """Create a snapshot of current state.

        Args:
            snapshot_type: Type of snapshot ('tidal', 'local', 'rekordbox')
            data: Snapshot data dictionary

        Returns:
            Created SyncSnapshot object
        """
        with self.get_session() as session:
            snapshot = SyncSnapshot(
                snapshot_type=snapshot_type,
                snapshot_data=json.dumps(data),
                playlist_count=data.get("playlist_count"),
                track_count=data.get("track_count"),
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            logger.info("Created %s snapshot (ID: %s)", snapshot_type, snapshot.id)
            return snapshot

    def get_latest_snapshot(self, snapshot_type: str) -> Optional[SyncSnapshot]:
        """Get the most recent snapshot of a given type.

        Args:
            snapshot_type: Type of snapshot

        Returns:
            SyncSnapshot object or None if not found
        """
        with self.get_session() as session:
            stmt = (
                select(SyncSnapshot)
                .where(SyncSnapshot.snapshot_type == snapshot_type)
                .order_by(SyncSnapshot.created_at.desc())
                .limit(1)
            )
            return session.scalar(stmt)

    def get_last_sync_timestamp(
        self, snapshot_type: str = "tidal_sync"
    ) -> Optional[datetime]:
        """Get the timestamp of the last sync snapshot.

        Args:
            snapshot_type: Type of snapshot (default: 'tidal_sync')

        Returns:
            Datetime of last sync or None if no snapshot exists
        """
        snapshot = self.get_latest_snapshot(snapshot_type)
        return snapshot.created_at if snapshot else None

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @staticmethod
    def _normalize_track_name(title: str, artist: str) -> str:
        """Normalize track name for comparison.

        Args:
            title: Track title
            artist: Track artist

        Returns:
            Normalized track name
        """
        import re

        # Normalize artist name - remove feat. parts
        artist_normalized = re.sub(
            r"\s*(feat\.?|featuring|ft\.?)\s+.*",
            "",
            artist,
            flags=re.IGNORECASE,
        )
        # Normalize title - remove remix, version, etc.
        title_normalized = re.sub(r"\s*\([^)]*\)\s*", "", title)
        title_normalized = re.sub(r"\s*\[[^\]]*\]\s*", "", title_normalized)
        artist_part = artist_normalized.lower().strip()
        title_part = title_normalized.lower().strip()
        return f"{artist_part} - {title_part}"

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            Hexadecimal hash string
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary with statistics
        """
        with self.get_session() as session:
            track_count = session.query(Track).count()
            playlist_count = session.query(Playlist).count()
            playlist_track_count = session.query(PlaylistTrack).count()
            pending_operations = (
                session.query(SyncOperation)
                .filter(SyncOperation.status == "pending")
                .count()
            )

            return {
                "tracks": track_count,
                "playlists": playlist_count,
                "playlist_tracks": playlist_track_count,
                "pending_operations": pending_operations,
                "database_path": str(self.db_path),
            }

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self, "engine"):
            self.engine.dispose()
            logger.info("Database connection closed")

    # Unified sync helper methods

    def get_tracks_by_download_status(
        self, status: str, limit: Optional[int] = None
    ) -> List[Track]:
        """Get tracks filtered by download status.

        Args:
            status: Download status (from DownloadStatus enum)
            limit: Optional limit on number of tracks returned

        Returns:
            List of Track objects
        """
        with self.get_session() as session:
            query = session.query(Track).filter(Track.download_status == status)
            if limit:
                query = query.limit(limit)
            return query.all()

    def get_playlists_by_sync_status(
        self, status: str, limit: Optional[int] = None
    ) -> List[Playlist]:
        """Get playlists filtered by sync status.

        Args:
            status: Sync status (from PlaylistSyncStatus enum)
            limit: Optional limit on number of playlists returned

        Returns:
            List of Playlist objects
        """
        with self.get_session() as session:
            query = session.query(Playlist).filter(Playlist.sync_status == status)
            if limit:
                query = query.limit(limit)
            return query.all()

    def update_track_download_status(
        self,
        track_id: int,
        status: str,
        error: Optional[str] = None,
        downloaded_at: Optional[datetime] = None,
    ) -> Track:
        """Update track download status.

        Args:
            track_id: Track database ID
            status: New download status (from DownloadStatus enum)
            error: Error message if status is 'error'
            downloaded_at: Download completion timestamp

        Returns:
            Updated Track object
        """
        update_data: Dict[str, Any] = {"download_status": status}

        if error is not None:
            update_data["download_error"] = error

        if downloaded_at is not None:
            update_data["downloaded_at"] = downloaded_at
        elif status == "downloaded" and downloaded_at is None:
            update_data["downloaded_at"] = datetime.now(timezone.utc)

        return self.update_track(track_id, update_data)

    def update_playlist_sync_status(
        self, playlist_id: int, status: str, synced_at: Optional[datetime] = None
    ) -> Playlist:
        """Update playlist sync status.

        Args:
            playlist_id: Playlist database ID
            status: New sync status (from PlaylistSyncStatus enum)
            synced_at: Sync completion timestamp

        Returns:
            Updated Playlist object
        """
        update_data: Dict[str, Any] = {"sync_status": status}

        if synced_at is not None:
            update_data["last_synced_filesystem"] = synced_at
        elif status == "in_sync":
            update_data["last_synced_filesystem"] = datetime.now(timezone.utc)

        return self.update_playlist(playlist_id, update_data)

    def get_tracks_needing_download(self) -> List[Track]:
        """Get all tracks that need to be downloaded.

        Returns:
            List of tracks with download_status='not_downloaded'
        """
        return self.get_tracks_by_download_status("not_downloaded")

    def get_tracks_with_errors(self) -> List[Track]:
        """Get all tracks with download errors.

        Returns:
            List of tracks with download_status='error'
        """
        return self.get_tracks_by_download_status("error")

    def get_playlists_needing_sync(self) -> List[Playlist]:
        """Get all playlists that need syncing.

        Returns:
            List of playlists with sync_status in
            (needs_download, needs_update, needs_removal)
        """
        with self.get_session() as session:
            return (
                session.query(Playlist)
                .filter(
                    Playlist.sync_status.in_(
                        ["needs_download", "needs_update", "needs_removal"]
                    )
                )
                .all()
            )

    def get_primary_playlist_tracks(self, playlist_id: int) -> List[PlaylistTrack]:
        """Get playlist tracks where this playlist has the primary file.

        Args:
            playlist_id: Playlist database ID

        Returns:
            List of PlaylistTrack objects where is_primary=True
        """
        with self.get_session() as session:
            return (
                session.query(PlaylistTrack)
                .filter(
                    PlaylistTrack.playlist_id == playlist_id,
                    PlaylistTrack.is_primary.is_(True),
                )
                .all()
            )

    def get_symlink_playlist_tracks(self, playlist_id: int) -> List[PlaylistTrack]:
        """Get playlist tracks where this playlist has symlinks.

        Args:
            playlist_id: Playlist database ID

        Returns:
            List of PlaylistTrack objects where is_primary=False
        """
        with self.get_session() as session:
            return (
                session.query(PlaylistTrack)
                .filter(
                    PlaylistTrack.playlist_id == playlist_id,
                    PlaylistTrack.is_primary.is_(False),
                )
                .all()
            )

    def get_broken_symlinks(self) -> List[PlaylistTrack]:
        """Get all playlist tracks with broken symlinks.

        Returns:
            List of PlaylistTrack objects where symlink_valid=False
        """
        with self.get_session() as session:
            return (
                session.query(PlaylistTrack)
                .filter(PlaylistTrack.symlink_valid.is_(False))
                .all()
            )

    def get_duplicate_tracks(self) -> Dict[int, List[PlaylistTrack]]:
        """Get tracks that appear in multiple playlists.

        Returns:
            Dictionary mapping track_id to list of PlaylistTrack objects
        """
        with self.get_session() as session:
            # Get all playlist tracks grouped by track_id
            all_pts = session.query(PlaylistTrack).all()

            # Group by track_id
            track_map: Dict[int, List[PlaylistTrack]] = {}
            for pt in all_pts:
                if pt.track_id not in track_map:
                    track_map[pt.track_id] = []
                track_map[pt.track_id].append(pt)

            # Filter to only tracks in multiple playlists
            return {
                track_id: pts for track_id, pts in track_map.items() if len(pts) > 1
            }

    def mark_playlist_track_as_primary(
        self, playlist_id: int, track_id: int
    ) -> PlaylistTrack | None:
        """Mark a playlist-track relationship as having the primary file.

        This will also mark all other occurrences of this track as non-primary.

        Args:
            playlist_id: Playlist database ID
            track_id: Track database ID

        Returns:
            Updated PlaylistTrack object, or None if not found
        """
        with self.get_session() as session:
            # Mark all occurrences as non-primary
            session.query(PlaylistTrack).filter(
                PlaylistTrack.track_id == track_id
            ).update({"is_primary": False})

            # Mark this one as primary
            pt = (
                session.query(PlaylistTrack)
                .filter(
                    PlaylistTrack.playlist_id == playlist_id,
                    PlaylistTrack.track_id == track_id,
                )
                .first()
            )

            if pt:
                pt.is_primary = True
                pt.sync_status = "synced"
                pt.synced_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(pt)

            return pt

    def update_symlink_status(
        self, playlist_id: int, track_id: int, symlink_path: str, valid: bool
    ) -> PlaylistTrack | None:
        """Update symlink information for a playlist-track relationship.

        Args:
            playlist_id: Playlist database ID
            track_id: Track database ID
            symlink_path: Full path to symlink
            valid: Whether symlink is valid

        Returns:
            Updated PlaylistTrack object, or None if not found
        """
        with self.get_session() as session:
            pt = (
                session.query(PlaylistTrack)
                .filter(
                    PlaylistTrack.playlist_id == playlist_id,
                    PlaylistTrack.track_id == track_id,
                )
                .first()
            )

            if pt:
                pt.symlink_path = symlink_path
                pt.symlink_valid = valid
                pt.is_primary = False
                pt.sync_status = "synced" if valid else "needs_symlink"
                pt.synced_at = datetime.now(timezone.utc) if valid else None
                session.commit()
                session.refresh(pt)

            return pt

    def get_sync_statistics(self) -> Dict[str, Any]:
        """Get comprehensive sync statistics.

        Returns:
            Dictionary with sync-related statistics
        """
        with self.get_session() as session:
            # Track statistics
            total_tracks = session.query(Track).count()
            downloaded = (
                session.query(Track)
                .filter(Track.download_status == "downloaded")
                .count()
            )
            not_downloaded = (
                session.query(Track)
                .filter(Track.download_status == "not_downloaded")
                .count()
            )
            downloading = (
                session.query(Track)
                .filter(Track.download_status == "downloading")
                .count()
            )
            errors = (
                session.query(Track).filter(Track.download_status == "error").count()
            )

            # Playlist statistics
            total_playlists = session.query(Playlist).count()
            in_sync = (
                session.query(Playlist)
                .filter(Playlist.sync_status == "in_sync")
                .count()
            )
            needs_download = (
                session.query(Playlist)
                .filter(Playlist.sync_status == "needs_download")
                .count()
            )
            needs_update = (
                session.query(Playlist)
                .filter(Playlist.sync_status == "needs_update")
                .count()
            )
            needs_removal = (
                session.query(Playlist)
                .filter(Playlist.sync_status == "needs_removal")
                .count()
            )

            # Deduplication statistics
            total_playlist_tracks = session.query(PlaylistTrack).count()
            primary_files = (
                session.query(PlaylistTrack)
                .filter(PlaylistTrack.is_primary.is_(True))
                .count()
            )
            symlinks = (
                session.query(PlaylistTrack)
                .filter(PlaylistTrack.is_primary.is_(False))
                .count()
            )
            broken_symlinks = (
                session.query(PlaylistTrack)
                .filter(PlaylistTrack.symlink_valid.is_(False))
                .count()
            )

            return {
                "tracks": {
                    "total": total_tracks,
                    "downloaded": downloaded,
                    "not_downloaded": not_downloaded,
                    "downloading": downloading,
                    "errors": errors,
                },
                "playlists": {
                    "total": total_playlists,
                    "in_sync": in_sync,
                    "needs_download": needs_download,
                    "needs_update": needs_update,
                    "needs_removal": needs_removal,
                },
                "deduplication": {
                    "total_playlist_tracks": total_playlist_tracks,
                    "primary_files": primary_files,
                    "symlinks": symlinks,
                    "broken_symlinks": broken_symlinks,
                },
                "database_path": str(self.db_path),
            }
