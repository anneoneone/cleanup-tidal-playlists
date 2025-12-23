"""Database service for managing playlist and track synchronization."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, joinedload, sessionmaker

from alembic import command  # type: ignore[attr-defined]
from alembic.config import Config as AlembicConfig  # type: ignore[import-not-found]

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

        # Check if database exists before creating engine
        db_exists = self.db_path.exists()

        # Create engine
        db_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(db_url, echo=False)

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

        logger.info("Database initialized at: %s", self.db_path)

        # If database didn't exist, initialize it with schema and migrations
        if not db_exists:
            logger.info("New database detected, initializing schema...")
            self.init_db()

    def init_db(self) -> None:
        """Initialize database schema.

        This creates base tables using SQLAlchemy and then stamps Alembic to mark the
        database as current (since all tables are created).
        """
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database schema created successfully")

        # Stamp database as being at latest migration (since we created all tables)
        self._stamp_migrations()

    def _stamp_migrations(self) -> None:
        """Stamp database as being at the latest migration version."""
        try:
            # Find alembic.ini and alembic directory in the project root
            package_dir = Path(__file__).parent.parent.parent.parent
            alembic_ini = package_dir / "alembic.ini"
            alembic_dir = package_dir / "alembic"

            if not alembic_ini.exists() or not alembic_dir.exists():
                logger.warning("Alembic not found, skipping migration stamp")
                return

            # Create Alembic config
            alembic_cfg = AlembicConfig(str(alembic_ini))
            alembic_cfg.set_main_option("script_location", str(alembic_dir))
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

            # Stamp database as being at head
            command.stamp(alembic_cfg, "head")
            logger.info("Database stamped with latest migration version")

        except Exception as e:
            logger.error("Failed to stamp migrations: %s", e)
            logger.warning("Database may need manual migration")

    def run_migrations(self) -> None:
        """Run Alembic migrations to upgrade database to latest version."""
        try:
            # Find alembic.ini and alembic directory in the project root
            # The database service is in src/tidal_cleanup/database/
            # alembic.ini and alembic/ are in project root
            package_dir = Path(__file__).parent.parent.parent.parent
            alembic_ini = package_dir / "alembic.ini"
            alembic_dir = package_dir / "alembic"

            if not alembic_ini.exists():
                logger.warning(
                    "alembic.ini not found at %s, skipping migrations", alembic_ini
                )
                return

            if not alembic_dir.exists():
                logger.warning(
                    "alembic directory not found at %s, skipping migrations",
                    alembic_dir,
                )
                return

            # Create Alembic config
            alembic_cfg = AlembicConfig(str(alembic_ini))

            # Set the script location to absolute path
            alembic_cfg.set_main_option("script_location", str(alembic_dir))

            # Override database URL to use our database path
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

            # Run upgrade to head
            command.upgrade(alembic_cfg, "head")
            logger.info("Database migrations applied successfully")

        except Exception as e:
            logger.error("Failed to run migrations: %s", e)
            # Don't fail completely - the base tables were created
            logger.warning("Continuing with base schema only")

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy Session object

        Note:
            Caller is responsible for closing the session
        """
        return self.SessionLocal()

    def is_initialized(self) -> bool:
        """Check if the database service is properly initialized.

        This checks:
        - SessionLocal exists and is callable
        - Engine exists and is connected
        - Required tables (tracks, playlists) exist

        Returns:
            True if fully initialized, False otherwise
        """
        try:
            # Check if SessionLocal exists and is callable
            if not hasattr(self, "SessionLocal") or not callable(self.SessionLocal):
                logger.debug("SessionLocal not properly set up")
                return False

            # Check if engine exists
            if not hasattr(self, "engine"):
                logger.debug("Engine not set up")
                return False

            # Check if required tables exist
            inspector = inspect(self.engine)
            has_tracks = inspector.has_table("tracks")
            has_playlists = inspector.has_table("playlists")

            if not (has_tracks and has_playlists):
                logger.debug(
                    "Required tables missing - tracks: %s, playlists: %s",
                    has_tracks,
                    has_playlists,
                )
                return False

            # Try to create a test session to verify configuration works
            with self.SessionLocal() as session:
                session.execute(select(1))

            return True
        except Exception as e:
            logger.debug("Database initialization check failed: %s", e)
            return False

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
            query = text(
                """
                SELECT tracks.id
                FROM tracks, json_each(tracks.file_paths) AS file_entry
                WHERE file_entry.value = :file_path
                LIMIT 1
                """
            )
            track_id = session.execute(
                query, {"file_path": file_path}
            ).scalar_one_or_none()
            if track_id is None:
                return None
            return session.get(Track, track_id)

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

    def create_or_update_track(self, track_data: Dict[str, Any]) -> Track:  # noqa: C901
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
                # If a new file path is provided, add it to the list
                new_path = track_data.get("file_path")
                if new_path:
                    # Remove file_path key; handled separately
                    track_data_copy = {
                        k: v for k, v in track_data.items() if k != "file_path"
                    }
                    updated_track = self.update_track(
                        existing_track.id, track_data_copy
                    )
                    # Add the new path to file_paths if not already present
                    self.add_file_path_to_track(updated_track.id, new_path)
                    return updated_track
                else:
                    return self.update_track(existing_track.id, track_data)

        # Try to find by file path
        file_path = track_data.get("file_path")
        if file_path:
            existing_track = self.get_track_by_path(file_path)
            if existing_track:
                # Remove file_path key to avoid conflicts
                track_data_copy = {
                    k: v for k, v in track_data.items() if k != "file_path"
                }
                updated_track = self.update_track(existing_track.id, track_data_copy)
                # Ensure the path is in the list
                self.add_file_path_to_track(updated_track.id, file_path)
                return updated_track

        # Try to find by metadata
        title = track_data.get("title")
        artist = track_data.get("artist")
        if title and artist:
            existing_track = self.find_track_by_metadata(title, artist)
            if existing_track:
                # Remove file_path key if present
                new_path = track_data.get("file_path")

                track_data_copy = {
                    k: v for k, v in track_data.items() if k != "file_path"
                }
                updated_track = self.update_track(existing_track.id, track_data_copy)
                if new_path:
                    self.add_file_path_to_track(updated_track.id, new_path)
                return updated_track

        # Create new track - convert file_path to file_paths list
        if "file_path" in track_data:
            file_path = track_data.pop("file_path")
            if "file_paths" not in track_data:
                track_data["file_paths"] = [file_path] if file_path else []
        return self.create_track(track_data)

    def add_file_path_to_track(self, track_id: int, file_path: str) -> Track:
        """Add a file path to track's file_paths list if not already present.

        Args:
            track_id: Track database ID
            file_path: File path to add (relative to MP3 directory)

        Returns:
            Updated Track object
        """
        with self.get_session() as session:
            track = session.get(Track, track_id)
            if not track:
                raise ValueError(f"Track not found: {track_id}")

            if file_path == "" or file_path is None:
                raise ValueError("File path cannot be empty")

            # Initialize file_paths if None
            if track.file_paths is None:
                track.file_paths = []

            # Add path if not already present
            if file_path not in track.file_paths:
                # Create new list to trigger SQLAlchemy update detection
                track.file_paths = track.file_paths + [file_path]
                track.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.debug(f"Added file path {file_path} to track {track_id}")

            session.refresh(track)
            return track

    def remove_file_path_from_track(self, track_id: int, file_path: str) -> Track:
        """Remove a file path from track's file_paths list.

        Args:
            track_id: Track database ID
            file_path: File path to remove

        Returns:
            Updated Track object
        """
        with self.get_session() as session:
            track = session.get(Track, track_id)
            if not track:
                raise ValueError(f"Track not found: {track_id}")

            # Remove path if present
            if track.file_paths and file_path in track.file_paths:
                # Create new list to trigger SQLAlchemy update detection
                track.file_paths = [p for p in track.file_paths if p != file_path]
                track.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.debug(f"Removed file path {file_path} from track {track_id}")

            session.refresh(track)
            return track

    def delete_track_if_unused(self, track_id: int) -> bool:
        """Delete a track if it has no file paths or playlist references."""
        with self.get_session() as session:
            track = session.get(Track, track_id)
            if not track:
                return False

            if track.file_paths:
                return False

            has_playlist = (
                session.query(PlaylistTrack)
                .filter(PlaylistTrack.track_id == track_id)
                .first()
                is not None
            )
            if has_playlist:
                return False

            session.delete(track)
            session.commit()
            logger.info("Deleted orphan track %s", track_id)
            return True

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

    def delete_playlist(self, playlist_id: int) -> None:
        """Delete a playlist and all related associations.

        Args:
            playlist_id: Playlist database ID
        """
        with self.get_session() as session:
            playlist = session.get(Playlist, playlist_id)
            if not playlist:
                logger.warning("Playlist not found for deletion: %s", playlist_id)
                return
            session.delete(playlist)
            session.commit()
            logger.info("Deleted playlist: %s", playlist_id)

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
                    playlist_track.in_tidal = bool(True)
                    if not playlist_track.added_to_tidal:
                        playlist_track.added_to_tidal = datetime.now(timezone.utc)
                if in_local:
                    playlist_track.in_local = bool(True)
                    if not playlist_track.added_to_local:
                        playlist_track.added_to_local = datetime.now(timezone.utc)
                if in_rekordbox:
                    playlist_track.in_rekordbox = bool(True)
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

    def get_playlist_tracks_with_tracks(
        self,
        playlist_id: Optional[int] = None,
        order_by_position: bool = False,
    ) -> List[PlaylistTrack]:
        """Fetch PlaylistTrack rows with Track eagerly loaded.

        Args:
            playlist_id: Optional playlist ID to filter by. If None, returns all.
            order_by_position: Whether to order results by playlist position

        Returns:
            List of PlaylistTrack objects with track relationship populated
        """
        with self.get_session() as session:
            query = session.query(PlaylistTrack).options(
                joinedload(PlaylistTrack.track)
            )

            if playlist_id is not None:
                query = query.filter(PlaylistTrack.playlist_id == playlist_id)

            if order_by_position:
                query = query.order_by(PlaylistTrack.position)

            return list(query.all())

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

    def mark_tracks_with_file_paths_as_local(
        self, playlist_id: Optional[int] = None
    ) -> int:
        """Mark playlist tracks as local if their Track has file paths.

        Args:
            playlist_id: Optional playlist ID filter

        Returns:
            Number of playlist tracks updated
        """
        with self.get_session() as session:
            stmt = select(PlaylistTrack).join(Track).where(Track.file_paths.isnot(None))

            if playlist_id is not None:
                stmt = stmt.where(PlaylistTrack.playlist_id == playlist_id)

            playlist_tracks = session.execute(stmt).scalars().all()

            marked_count = 0
            for pt in playlist_tracks:
                if not pt.in_local:
                    pt.in_local = True
                    marked_count += 1

            session.commit()
            logger.debug(
                f"Marked {marked_count} playlist tracks as in_local"
                f"{' for playlist ' + str(playlist_id) if playlist_id else ''}"
            )
            return marked_count

    def mark_tracks_with_rekordbox_ids(self, playlist_id: Optional[int] = None) -> int:
        """Mark playlist tracks as present in Rekordbox when content IDs exist.

        Args:
            playlist_id: Optional playlist ID filter

        Returns:
            Number of playlist tracks updated
        """
        with self.get_session() as session:
            stmt = (
                select(PlaylistTrack)
                .join(Track)
                .where(Track.rekordbox_content_id.isnot(None))
            )

            if playlist_id is not None:
                stmt = stmt.where(PlaylistTrack.playlist_id == playlist_id)

            playlist_tracks = session.execute(stmt).scalars().all()

            marked_count = 0
            for pt in playlist_tracks:
                if not pt.in_rekordbox:
                    pt.in_rekordbox = True
                    marked_count += 1

            session.commit()
            logger.debug(
                f"Marked {marked_count} playlist tracks as in_rekordbox"
                f"{' for playlist ' + str(playlist_id) if playlist_id else ''}"
            )
            return marked_count

    def set_playlist_rekordbox_id(
        self, playlist_id: int, rekordbox_playlist_id: Optional[str]
    ) -> bool:
        """Update the Rekordbox playlist identifier for a playlist."""
        with self.get_session() as session:
            playlist = session.get(Playlist, playlist_id)
            if not playlist:
                logger.warning(
                    "Playlist not found while setting Rekordbox ID: %s", playlist_id
                )
                return False

            playlist.rekordbox_playlist_id = (
                str(rekordbox_playlist_id) if rekordbox_playlist_id else None
            )
            session.commit()
            logger.debug(
                "Playlist %s Rekordbox ID set to %s",
                playlist_id,
                playlist.rekordbox_playlist_id,
            )
            return True

    def set_track_rekordbox_id(
        self, track_id: int, rekordbox_content_id: Optional[str]
    ) -> bool:
        """Update the Rekordbox content identifier for a track."""
        with self.get_session() as session:
            track = session.get(Track, track_id)
            if not track:
                logger.warning(
                    "Track not found while setting Rekordbox content ID: %s",
                    track_id,
                )
                return False

            track.rekordbox_content_id = (
                str(rekordbox_content_id) if rekordbox_content_id else None
            )
            session.commit()
            logger.debug(
                "Track %s Rekordbox content ID set to %s",
                track_id,
                track.rekordbox_content_id,
            )
            return True

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

            # Get names for readable logging
            playlist_name = self.get_playlist_name(playlist_id)
            track_name = self.get_track_name(track_id)

            if not playlist_track:
                logger.warning(
                    f"PlaylistTrack not found: "
                    f"playlist={playlist_name}(id={playlist_id}), "
                    f"track={track_name}(id={track_id})"
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
                f"Updated track sync state: playlist='{playlist_name}', "
                f"track='{track_name}' (in_tidal={in_tidal}, in_local={in_local}, "
                f"in_rekordbox={in_rekordbox})"
            )
            return True

    def clear_playlist_track_flag(
        self,
        flag_name: str,
        playlist_name: Optional[str] = None,
    ) -> int:
        """Clear a specific flag for playlist tracks.

        This method sets a boolean flag (in_tidal, in_local, or in_rekordbox)
        to False for all playlist tracks, or only those in a specific playlist.

        Args:
            flag_name: Name of flag to clear ('in_tidal', 'in_local',
                      'in_rekordbox')
            playlist_name: Optional playlist name to filter by.
                          If None, clears flag for all playlists.

        Returns:
            Number of playlist tracks updated

        Raises:
            ValueError: If flag_name is not valid
        """
        valid_flags = {"in_tidal", "in_local", "in_rekordbox"}
        if flag_name not in valid_flags:
            raise ValueError(
                f"Invalid flag name: {flag_name}. Must be one of {valid_flags}"
            )

        with self.get_session() as session:
            query = session.query(PlaylistTrack)

            # Filter by playlist if specified
            if playlist_name:
                playlist_obj = self.get_playlist_by_name(playlist_name)
                if playlist_obj:
                    logger.debug(
                        f"Clearing {flag_name} flags for playlist '{playlist_name}' "
                        f"(ID: {playlist_obj.id})"
                    )
                    query = query.filter(PlaylistTrack.playlist_id == playlist_obj.id)
                else:
                    logger.warning(f"Playlist '{playlist_name}' not found in database")
                    return 0
            else:
                logger.debug(f"Clearing {flag_name} flags for all playlists")

            # Update flag to False (0)
            reset_count = query.update({flag_name: 0})
            session.commit()
            logger.debug(f"Cleared {flag_name} flag for {reset_count} playlist tracks")

            return reset_count

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

    def get_playlist_name(self, playlist_id: int) -> str:
        """Get playlist name by ID for logging/display.

        Args:
            playlist_id: Playlist database ID

        Returns:
            Playlist name or formatted ID if not found
        """
        playlist = self.get_playlist_by_id(playlist_id)
        return playlist.name if playlist else f"ID:{playlist_id}"

    def get_track_name(self, track_id: int) -> str:
        """Get track name by ID for logging/display.

        Args:
            track_id: Track database ID

        Returns:
            Formatted track name (Artist - Title) or ID if not found
        """
        track = self.get_track_by_id(track_id)
        return f"{track.artist} - {track.title}" if track else f"ID:{track_id}"

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

    def track_has_active_playlist(self, track_id: int) -> bool:
        """Return True if track still belongs to any Tidal playlist."""
        with self.get_session() as session:
            from .models import PlaylistTrack

            return (
                session.query(PlaylistTrack)
                .filter(
                    PlaylistTrack.track_id == track_id,
                    PlaylistTrack.in_tidal.is_(True),
                )
                .first()
                is not None
            )

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
                },
                "database_path": str(self.db_path),
            }
