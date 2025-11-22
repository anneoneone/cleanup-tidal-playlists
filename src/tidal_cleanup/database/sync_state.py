"""Sync State Tracking System.

This module provides the core change detection logic for tracking differences between
Tidal (source of truth), local files, and Rekordbox database state.
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .models import Playlist, PlaylistTrack, Track


class ChangeType(str, Enum):
    """Types of changes that can occur during sync."""

    # Playlist-level changes
    PLAYLIST_ADDED = "playlist_added"
    PLAYLIST_REMOVED = "playlist_removed"
    PLAYLIST_RENAMED = "playlist_renamed"
    PLAYLIST_DESCRIPTION_CHANGED = "playlist_description_changed"

    # Track-level changes (within playlists)
    TRACK_ADDED_TO_PLAYLIST = "track_added_to_playlist"
    TRACK_REMOVED_FROM_PLAYLIST = "track_removed_from_playlist"
    TRACK_MOVED_WITHIN_PLAYLIST = "track_moved_within_playlist"
    TRACK_MOVED_BETWEEN_PLAYLISTS = "track_moved_between_playlists"

    # Track metadata changes
    TRACK_METADATA_CHANGED = "track_metadata_changed"
    TRACK_ADDED = "track_added"
    TRACK_REMOVED = "track_removed"

    # File-level changes
    FILE_ADDED = "file_added"
    FILE_REMOVED = "file_removed"
    FILE_MOVED = "file_moved"
    FILE_HASH_CHANGED = "file_hash_changed"

    # Rekordbox-level changes
    REKORDBOX_SYNC_NEEDED = "rekordbox_sync_needed"
    REKORDBOX_TRACK_MISSING = "rekordbox_track_missing"


@dataclass
class Change:
    """Represents a single detected change in the sync state.

    Attributes:
        change_type: The type of change detected
        entity_type: What entity changed (playlist, track, file)
        entity_id: Database ID of the affected entity (if applicable)
        old_value: Previous value (if applicable)
        new_value: New value (if applicable)
        playlist_id: Related playlist ID (if applicable)
        track_id: Related track ID (if applicable)
        metadata: Additional context about the change
        detected_at: When this change was detected
    """

    change_type: ChangeType
    entity_type: str  # "playlist", "track", "file", "rekordbox"
    entity_id: Optional[int] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    playlist_id: Optional[int] = None
    track_id: Optional[int] = None
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)
    detected_at: datetime = dataclass_field(default_factory=datetime.now)

    def __str__(self) -> str:
        """Human-readable representation of the change."""
        parts = [f"[{self.change_type.value}]"]

        if self.entity_type:
            parts.append(f"{self.entity_type}")

        if self.entity_id:
            parts.append(f"(ID: {self.entity_id})")

        if self.old_value and self.new_value:
            parts.append(f": {self.old_value} → {self.new_value}")
        elif self.new_value:
            parts.append(f": {self.new_value}")
        elif self.old_value:
            parts.append(f": {self.old_value}")

        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert change to dictionary for serialization."""
        return {
            "change_type": self.change_type.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "playlist_id": self.playlist_id,
            "track_id": self.track_id,
            "metadata": self.metadata,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class SyncState:
    """Represents the current sync state across all sources.

    Attributes:
        changes: List of detected changes
        tidal_playlists_count: Number of playlists in Tidal
        tidal_tracks_count: Number of unique tracks in Tidal
        local_files_count: Number of local MP3 files
        rekordbox_playlists_count: Number of playlists in Rekordbox
        database_tracks_count: Number of tracks in database
        database_playlists_count: Number of playlists in database
        last_tidal_sync: Last time Tidal was synced
        last_file_scan: Last time files were scanned
        last_rekordbox_sync: Last time Rekordbox was synced
    """

    changes: list[Change] = dataclass_field(default_factory=list)
    tidal_playlists_count: int = 0
    tidal_tracks_count: int = 0
    local_files_count: int = 0
    rekordbox_playlists_count: int = 0
    database_tracks_count: int = 0
    database_playlists_count: int = 0
    last_tidal_sync: Optional[datetime] = None
    last_file_scan: Optional[datetime] = None
    last_rekordbox_sync: Optional[datetime] = None

    def add_change(self, change: Change) -> None:
        """Add a change to the sync state."""
        self.changes.append(change)

    def get_changes_by_type(self, change_type: ChangeType) -> list[Change]:
        """Get all changes of a specific type."""
        return [c for c in self.changes if c.change_type == change_type]

    def get_changes_by_entity(
        self, entity_type: str, entity_id: Optional[int] = None
    ) -> list[Change]:
        """Get all changes for a specific entity.

        Args:
            entity_type: Type of entity ("playlist", "track", "file")
            entity_id: Optional specific entity ID to filter by
        """
        if entity_id is not None:
            return [
                c
                for c in self.changes
                if c.entity_type == entity_type and c.entity_id == entity_id
            ]
        return [c for c in self.changes if c.entity_type == entity_type]

    def get_playlist_changes(self, playlist_id: Optional[int] = None) -> list[Change]:
        """Get all changes related to a specific playlist or all playlists."""
        if playlist_id is not None:
            return [
                c
                for c in self.changes
                if c.playlist_id == playlist_id
                or (c.entity_type == "playlist" and c.entity_id == playlist_id)
            ]
        return [
            c
            for c in self.changes
            if c.entity_type == "playlist" or c.playlist_id is not None
        ]

    def get_track_changes(self, track_id: Optional[int] = None) -> list[Change]:
        """Get all changes related to a specific track or all tracks."""
        if track_id is not None:
            return [
                c
                for c in self.changes
                if c.track_id == track_id
                or (c.entity_type == "track" and c.entity_id == track_id)
            ]
        return [
            c
            for c in self.changes
            if c.entity_type == "track" or c.track_id is not None
        ]

    def has_changes(self) -> bool:
        """Check if any changes were detected."""
        return len(self.changes) > 0

    def get_summary(self) -> dict[str, int]:
        """Get a summary of changes by type."""
        summary: dict[str, int] = {}
        for change in self.changes:
            change_type = change.change_type.value
            summary[change_type] = summary.get(change_type, 0) + 1
        return summary

    def to_dict(self) -> dict[str, Any]:
        """Convert sync state to dictionary for serialization."""
        return {
            "changes": [c.to_dict() for c in self.changes],
            "summary": self.get_summary(),
            "counts": {
                "tidal_playlists": self.tidal_playlists_count,
                "tidal_tracks": self.tidal_tracks_count,
                "local_files": self.local_files_count,
                "rekordbox_playlists": self.rekordbox_playlists_count,
                "database_tracks": self.database_tracks_count,
                "database_playlists": self.database_playlists_count,
            },
            "last_sync_times": {
                "tidal": (
                    self.last_tidal_sync.isoformat() if self.last_tidal_sync else None
                ),
                "files": (
                    self.last_file_scan.isoformat() if self.last_file_scan else None
                ),
                "rekordbox": (
                    self.last_rekordbox_sync.isoformat()
                    if self.last_rekordbox_sync
                    else None
                ),
            },
        }


class SyncStateComparator:
    """Compares database state with snapshots to detect changes.

    This class provides methods to compare the current database state with previous
    snapshots from Tidal, local files, or Rekordbox.
    """

    def compare_playlists(
        self,
        db_playlists: list[Playlist],
        snapshot_playlists: list[dict[str, Any]],
    ) -> list[Change]:
        """Compare database playlists with snapshot playlists.

        Args:
            db_playlists: Current playlists from database
            snapshot_playlists: Playlists from snapshot (dict with tidal_id, name, etc.)

        Returns:
            List of detected changes
        """
        changes: list[Change] = []

        # Create lookup maps
        db_map = {p.tidal_id: p for p in db_playlists}
        snapshot_map = {p["tidal_id"]: p for p in snapshot_playlists}

        # Check for new playlists in snapshot
        for tidal_id, snapshot_pl in snapshot_map.items():
            if tidal_id not in db_map:
                changes.append(
                    Change(
                        change_type=ChangeType.PLAYLIST_ADDED,
                        entity_type="playlist",
                        new_value=snapshot_pl["name"],
                        metadata={"tidal_id": tidal_id},
                    )
                )
            else:
                # Check for playlist name changes
                db_pl = db_map[tidal_id]
                if db_pl.name != snapshot_pl["name"]:
                    changes.append(
                        Change(
                            change_type=ChangeType.PLAYLIST_RENAMED,
                            entity_type="playlist",
                            entity_id=db_pl.id,
                            old_value=db_pl.name,
                            new_value=snapshot_pl["name"],
                            metadata={"tidal_id": tidal_id},
                        )
                    )

                # Check for description changes
                if db_pl.description != snapshot_pl.get("description"):
                    changes.append(
                        Change(
                            change_type=ChangeType.PLAYLIST_DESCRIPTION_CHANGED,
                            entity_type="playlist",
                            entity_id=db_pl.id,
                            old_value=db_pl.description,
                            new_value=snapshot_pl.get("description"),
                            metadata={"tidal_id": tidal_id},
                        )
                    )

        # Check for removed playlists
        for tidal_id, db_pl in db_map.items():
            if tidal_id not in snapshot_map:
                changes.append(
                    Change(
                        change_type=ChangeType.PLAYLIST_REMOVED,
                        entity_type="playlist",
                        entity_id=db_pl.id,
                        old_value=db_pl.name,
                        metadata={"tidal_id": tidal_id},
                    )
                )

        return changes

    def compare_playlist_tracks(
        self,
        db_tracks: list[PlaylistTrack],
        snapshot_tracks: list[dict[str, Any]],
        playlist_id: int,
    ) -> list[Change]:
        """Compare tracks within a playlist.

        Args:
            db_tracks: Current playlist tracks from database
            snapshot_tracks: Tracks from snapshot (dict with tidal_id, position)
            playlist_id: Database ID of the playlist

        Returns:
            List of detected changes
        """
        changes: list[Change] = []

        # Create lookup maps by tidal_id
        db_map = {pt.track.tidal_id: pt for pt in db_tracks if pt.track}
        snapshot_map = {t["tidal_id"]: t for t in snapshot_tracks}

        # Check for new tracks
        for tidal_id, snapshot_track in snapshot_map.items():
            if tidal_id not in db_map:
                changes.append(
                    Change(
                        change_type=ChangeType.TRACK_ADDED_TO_PLAYLIST,
                        entity_type="track",
                        new_value=f"{snapshot_track.get('artist', 'Unknown')} - "
                        f"{snapshot_track.get('title', 'Unknown')}",
                        playlist_id=playlist_id,
                        metadata={
                            "tidal_id": tidal_id,
                            "position": snapshot_track.get("position", 0),
                        },
                    )
                )
            else:
                # Check for position changes
                db_pt = db_map[tidal_id]
                snapshot_pos = snapshot_track.get("position", 0)
                if db_pt.position != snapshot_pos:
                    changes.append(
                        Change(
                            change_type=ChangeType.TRACK_MOVED_WITHIN_PLAYLIST,
                            entity_type="track",
                            entity_id=db_pt.track_id,
                            old_value=db_pt.position,
                            new_value=snapshot_pos,
                            playlist_id=playlist_id,
                            track_id=db_pt.track_id,
                            metadata={"tidal_id": tidal_id},
                        )
                    )

        # Check for removed tracks
        for tidal_id, db_pt in db_map.items():
            if tidal_id not in snapshot_map:
                track_name = "Unknown"
                if db_pt.track:
                    track_name = f"{db_pt.track.artist} - {db_pt.track.title}"
                changes.append(
                    Change(
                        change_type=ChangeType.TRACK_REMOVED_FROM_PLAYLIST,
                        entity_type="track",
                        entity_id=db_pt.track_id,
                        old_value=track_name,
                        playlist_id=playlist_id,
                        track_id=db_pt.track_id,
                        metadata={"tidal_id": tidal_id},
                    )
                )

        return changes

    def compare_track_metadata(
        self,
        db_track: Track,
        snapshot_track: dict[str, Any],
    ) -> list[Change]:
        """Compare track metadata for changes.

        Args:
            db_track: Current track from database
            snapshot_track: Track data from snapshot

        Returns:
            List of detected metadata changes
        """
        changes: list[Change] = []
        metadata_changes = {}

        # Check each metadata field
        fields_to_check = [
            "title",
            "artist",
            "album",
            "album_artist",
            "genre",
            "year",
            "duration",
            "isrc",
        ]

        for field_name in fields_to_check:
            db_value = getattr(db_track, field_name, None)
            snapshot_value = snapshot_track.get(field_name)

            if db_value != snapshot_value and snapshot_value is not None:
                metadata_changes[field_name] = {
                    "old": db_value,
                    "new": snapshot_value,
                }

        if metadata_changes:
            changes.append(
                Change(
                    change_type=ChangeType.TRACK_METADATA_CHANGED,
                    entity_type="track",
                    entity_id=db_track.id,
                    old_value=str(metadata_changes),
                    new_value=f"{db_track.artist} - {db_track.title}",
                    track_id=db_track.id,
                    metadata={
                        "tidal_id": db_track.tidal_id,
                        "changes": metadata_changes,
                    },
                )
            )

        return changes
