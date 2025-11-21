"""SQLAlchemy database models for playlist and track synchronization."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class DownloadStatus(str, Enum):
    """Track download status for unified sync."""

    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"


class PlaylistSyncStatus(str, Enum):
    """Playlist sync status for unified Tidal-Filesystem sync."""

    IN_SYNC = "in_sync"
    NEEDS_DOWNLOAD = "needs_download"
    NEEDS_UPDATE = "needs_update"
    NEEDS_REMOVAL = "needs_removal"
    UNKNOWN = "unknown"


class TrackSyncStatus(str, Enum):
    """PlaylistTrack sync status for unified sync."""

    SYNCED = "synced"
    NEEDS_SYMLINK = "needs_symlink"
    NEEDS_MOVE = "needs_move"
    NEEDS_REMOVAL = "needs_removal"
    UNKNOWN = "unknown"


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Track(Base):
    """Represents a music track across Tidal, local files, and Rekordbox."""

    __tablename__ = "tracks"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Tidal identifiers
    tidal_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )

    # Track metadata (basic)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artist: Mapped[str] = mapped_column(String(500), nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    album_artist: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # seconds
    isrc: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # International Standard Recording Code

    # Tidal-specific metadata
    track_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    volume_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    explicit: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    popularity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    copyright: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tidal_release_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    audio_quality: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., 'HI_RES', 'LOSSLESS'
    audio_modes: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., 'STEREO', 'DOLBY_ATMOS'
    version: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )  # e.g., 'Radio Edit', 'Remix'

    # Album metadata (for quick access without joining)
    album_upc: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # Universal Product Code
    album_release_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    album_cover_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Tidal cover image URL

    # Computed fields for matching
    normalized_name: Mapped[str] = mapped_column(
        String(1000), nullable=False, index=True
    )

    # File information
    file_path: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True, index=True
    )  # Primary file location (actual audio data) - relative to MP3 directory
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_format: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    file_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # SHA256 hash
    file_last_modified: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Download state (unified sync)
    download_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DownloadStatus.NOT_DOWNLOADED.value,
        index=True,
    )  # Enum: not_downloaded, downloading, downloaded, error
    download_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # Error message if download failed
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # When file was successfully downloaded
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # Last integrity verification

    # Rekordbox integration
    rekordbox_content_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_seen_in_tidal: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Relationships
    playlist_tracks: Mapped[List["PlaylistTrack"]] = relationship(
        "PlaylistTrack", back_populates="track", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_artist_title", "artist", "title"),
        Index("idx_normalized_name", "normalized_name"),
    )

    def __repr__(self) -> str:
        """String representation of Track."""
        return f"<Track(id={self.id}, title='{self.title}', artist='{self.artist}')>"


class Playlist(Base):
    """Represents a playlist across Tidal, local files, and Rekordbox."""

    __tablename__ = "playlists"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Tidal identifiers
    tidal_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # Playlist metadata
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Tidal-specific playlist metadata
    creator_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    creator_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Total duration in seconds
    num_tracks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_videos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    popularity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    public: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    picture_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Tidal playlist image URL
    square_picture_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    created: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # When created in Tidal
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # When last updated in Tidal
    last_item_added_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    share_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    listen_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Local mapping
    local_folder_path: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )  # Filesystem location: mp3/Playlists/{sanitized_name}/

    # Rekordbox integration
    rekordbox_playlist_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # Sync state (unified Tidal-Filesystem sync)
    sync_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PlaylistSyncStatus.UNKNOWN.value,
        index=True,
    )  # Enum: in_sync, needs_download, needs_update, needs_removal, unknown
    last_updated_tidal: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # When playlist was last modified in Tidal (from API)
    last_synced_filesystem: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # When we last synced this playlist to filesystem

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_seen_in_tidal: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Metadata (cached counts)
    track_count_tidal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    track_count_local: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    track_count_rekordbox: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Relationships
    playlist_tracks: Mapped[List["PlaylistTrack"]] = relationship(
        "PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation of Playlist."""
        return (
            f"<Playlist(id={self.id}, name='{self.name}', "
            f"tidal_id='{self.tidal_id}')>"
        )


class PlaylistTrack(Base):
    """Many-to-many relationship between playlists and tracks."""

    __tablename__ = "playlist_tracks"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )

    # Ordering
    position: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Track position in playlist (Tidal order)

    # Source tracking
    in_tidal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    in_local: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    in_rekordbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Deduplication and symlink tracking (unified sync)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # True if this playlist has the primary file (actual audio data)
    symlink_path: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )  # Full path to symlink if is_primary=False
    symlink_valid: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )  # False if symlink exists but target missing/broken
    sync_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TrackSyncStatus.UNKNOWN.value,
        index=True,
    )  # Enum: synced, needs_symlink, needs_move, needs_removal, unknown
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # When this playlist-track relationship was last synced to filesystem

    # Timestamps
    added_to_tidal: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    added_to_local: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    added_to_rekordbox: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    removed_from_tidal: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    playlist: Mapped["Playlist"] = relationship(
        "Playlist", back_populates="playlist_tracks"
    )
    track: Mapped["Track"] = relationship("Track", back_populates="playlist_tracks")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("playlist_id", "track_id", name="uq_playlist_track"),
        Index("idx_playlist", "playlist_id"),
        Index("idx_track", "track_id"),
        Index("idx_sync_state", "in_tidal", "in_local", "in_rekordbox"),
    )

    def __repr__(self) -> str:
        """String representation of PlaylistTrack."""
        return (
            f"<PlaylistTrack(id={self.id}, playlist_id={self.playlist_id}, "
            f"track_id={self.track_id}, position={self.position})>"
        )


class SyncOperation(Base):
    """Represents a sync operation or pending action."""

    __tablename__ = "sync_operations"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Operation type and status
    operation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'snapshot', 'download', 'sync_rekordbox', 'cleanup'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # 'pending', 'running', 'completed', 'failed'

    # Target information
    playlist_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=True
    )
    track_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=True
    )

    # Operation details
    action: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # 'add', 'remove', 'update', 'move'
    source: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # 'tidal', 'local', 'rekordbox'
    target: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # 'tidal', 'local', 'rekordbox'

    # Results
    details: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON with operation details
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    playlist: Mapped[Optional["Playlist"]] = relationship("Playlist")
    track: Mapped[Optional["Track"]] = relationship("Track")

    def __repr__(self) -> str:
        """String representation of SyncOperation."""
        return (
            f"<SyncOperation(id={self.id}, type='{self.operation_type}', "
            f"status='{self.status}')>"
        )


class SyncSnapshot(Base):
    """Represents a point-in-time snapshot of sync state."""

    __tablename__ = "sync_snapshots"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Snapshot details
    snapshot_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'tidal', 'local', 'rekordbox'
    snapshot_data: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON dump of state

    # Statistics
    playlist_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    track_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Indexes
    __table_args__ = (Index("idx_type_created", "snapshot_type", "created_at"),)

    def __repr__(self) -> str:
        """String representation of SyncSnapshot."""
        return (
            f"<SyncSnapshot(id={self.id}, type='{self.snapshot_type}', "
            f"created_at='{self.created_at}')>"
        )
