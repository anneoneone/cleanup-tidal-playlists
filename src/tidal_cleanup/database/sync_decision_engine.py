"""Sync Decision Engine for comparing Tidal state vs Filesystem state.

This module implements the decision logic that determines what actions need to be taken
to synchronize playlists between Tidal and the filesystem.
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from .models import DownloadStatus, Track
from .service import DatabaseService

logger = logging.getLogger(__name__)


class SyncAction(str, Enum):
    """Actions that can be taken to synchronize tracks and playlists."""

    # Track-level actions
    DOWNLOAD_TRACK = "download_track"  # Download track from Tidal
    UPDATE_METADATA = "update_metadata"  # Update track metadata
    REMOVE_FILE = "remove_file"  # Remove file no longer in Tidal
    VERIFY_FILE = "verify_file"  # Verify file integrity

    # PlaylistTrack-level actions
    CREATE_SYMLINK = "create_symlink"  # Create symlink to primary file
    UPDATE_SYMLINK = "update_symlink"  # Update broken/incorrect symlink
    REMOVE_SYMLINK = "remove_symlink"  # Remove symlink no longer needed
    MARK_PRIMARY = "mark_primary"  # Mark this playlist as having primary file

    # Playlist-level actions
    CREATE_PLAYLIST_DIR = "create_playlist_dir"  # Create playlist directory
    REMOVE_PLAYLIST_DIR = "remove_playlist_dir"  # Remove empty playlist dir
    SYNC_PLAYLIST = "sync_playlist"  # General playlist sync

    # No action
    NO_ACTION = "no_action"  # Everything is in sync


@dataclass
class DecisionResult:
    """Result of a sync decision analysis."""

    # Action to take
    action: SyncAction

    # Context information
    track_id: int | None = None
    playlist_id: int | None = None
    playlist_track_id: int | None = None

    # Paths involved
    source_path: str | None = None
    target_path: str | None = None

    # Reason for the decision
    reason: str = ""

    # Priority (higher = more urgent)
    priority: int = 0

    # Additional metadata
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass
class SyncDecisions:
    """Collection of sync decisions with statistics."""

    decisions: List[DecisionResult] = dataclass_field(default_factory=list)

    # Statistics
    tracks_to_download: int = 0
    symlinks_to_create: int = 0
    symlinks_to_update: int = 0
    files_to_remove: int = 0
    metadata_updates: int = 0
    no_action_needed: int = 0

    def add_decision(self, decision: DecisionResult) -> None:
        """Add a decision and update statistics."""
        self.decisions.append(decision)

        # Update statistics based on action
        if decision.action == SyncAction.DOWNLOAD_TRACK:
            self.tracks_to_download += 1
        elif decision.action == SyncAction.CREATE_SYMLINK:
            self.symlinks_to_create += 1
        elif decision.action == SyncAction.UPDATE_SYMLINK:
            self.symlinks_to_update += 1
        elif decision.action == SyncAction.REMOVE_FILE:
            self.files_to_remove += 1
        elif decision.action == SyncAction.UPDATE_METADATA:
            self.metadata_updates += 1
        elif decision.action == SyncAction.NO_ACTION:
            self.no_action_needed += 1

    def get_summary(self) -> Dict[str, int]:
        """Get summary statistics."""
        return {
            "total_decisions": len(self.decisions),
            "tracks_to_download": self.tracks_to_download,
            "symlinks_to_create": self.symlinks_to_create,
            "symlinks_to_update": self.symlinks_to_update,
            "files_to_remove": self.files_to_remove,
            "metadata_updates": self.metadata_updates,
            "no_action_needed": self.no_action_needed,
        }


class SyncDecisionEngine:
    """Decision engine for determining sync actions.

    Analyzes the current state of tracks and playlists in the database (populated by
    TidalStateFetcher and FilesystemScanner) and decides what actions need to be taken
    to achieve synchronization.
    """

    def __init__(self, db_service: DatabaseService, music_root: Path | str):
        """Initialize the decision engine.

        Args:
            db_service: Database service instance
            music_root: Root directory for music files (contains Playlists/)
        """
        self.db_service = db_service
        self.music_root = Path(music_root)
        self.playlists_root = self.music_root / "Playlists"

    def analyze_playlist_sync(self, playlist_id: int) -> SyncDecisions:
        """Analyze sync status for a single playlist.

        Args:
            playlist_id: Database ID of the playlist

        Returns:
            SyncDecisions object with all decisions for this playlist
        """
        decisions = SyncDecisions()

        # Get playlist
        playlist = self.db_service.get_playlist_by_id(playlist_id)
        if not playlist:
            logger.warning("Playlist %d not found", playlist_id)
            return decisions

        # Get all playlist-track associations
        playlist_tracks = self.db_service.get_playlist_track_associations(playlist_id)

        for pt in playlist_tracks:
            track = pt.track
            if not track:
                logger.warning("Track not found for PlaylistTrack %s", pt.id)
                continue

            # Decide action for this track in this playlist
            decision = self._decide_playlist_track_action(playlist, track, pt)
            decisions.add_decision(decision)

        return decisions

    def analyze_all_playlists(self) -> SyncDecisions:
        """Analyze sync status for all playlists.

        Returns:
            SyncDecisions object with all decisions for all playlists
        """
        decisions = SyncDecisions()

        # Get all playlists
        playlists = self.db_service.get_all_playlists()

        logger.info("Analyzing %d playlists for sync decisions", len(playlists))

        for playlist in playlists:
            playlist_decisions = self.analyze_playlist_sync(playlist.id)
            # Merge decisions
            for decision in playlist_decisions.decisions:
                decisions.add_decision(decision)

        logger.info(
            f"Analysis complete: {len(decisions.decisions)} total decisions, "
            f"{decisions.tracks_to_download} tracks to download"
        )

        return decisions

    def _decide_playlist_track_action(
        self, playlist: Any, track: Track, playlist_track: Any
    ) -> DecisionResult:
        """Decide what action to take for a track in a playlist.

        Args:
            playlist: Playlist object
            track: Track object
            playlist_track: PlaylistTrack association object

        Returns:
            DecisionResult with the action to take
        """
        # Check if track needs to be downloaded
        if track.download_status == DownloadStatus.NOT_DOWNLOADED:
            return self._decide_download_action(playlist, track, playlist_track)

        # Check if track is in error state - retry download
        if track.download_status == DownloadStatus.ERROR:
            decision = self._decide_download_action(playlist, track, playlist_track)
            # Update reason and priority for retry
            decision.reason = "Track download previously failed, retry needed"
            decision.priority = 5
            return decision

        # Track is downloaded, check if file exists
        if not track.file_path or not Path(track.file_path).exists():
            decision = self._decide_download_action(playlist, track, playlist_track)
            # Update reason and priority for missing file
            decision.reason = "Track marked as downloaded but file missing"
            decision.priority = 8
            return decision

        # Track exists, check playlist-track sync status
        return self._decide_symlink_action(playlist, track, playlist_track)

    def _decide_download_action(
        self, playlist: Any, track: Track, playlist_track: Any
    ) -> DecisionResult:
        """Decide download action for a track.

        Args:
            playlist: Playlist object
            track: Track object
            playlist_track: PlaylistTrack association object

        Returns:
            DecisionResult with download action or NO_ACTION if file exists
        """
        # Validate track has required metadata
        if not track.artist or not track.title:
            logger.warning(
                f"Track {track.id} missing artist or title, skipping download"
            )
            return DecisionResult(
                action=SyncAction.NO_ACTION,
                track_id=track.id,
                playlist_id=playlist.id,
                playlist_track_id=playlist_track.id,
                reason=f"Track missing metadata (artist: {track.artist}, "
                f"title: {track.title})",
                priority=0,
            )

        # Determine where to download
        playlist_dir = self.playlists_root / playlist.name

        # Construct filename using artist - title format (matches tidal-dl-ng)
        # Use original Tidal metadata, not normalized name
        base_filename = f"{track.artist} - {track.title}"

        # Determine target extension from music_root path
        # e.g., if music_root is /path/to/mp3, use .mp3
        target_format = self.music_root.name  # Gets last part of path
        target_ext = f".{target_format}"

        filename = f"{base_filename}{target_ext}"
        target_path = playlist_dir / filename

        # Check if file already exists at target location
        # Use a more flexible check since tidal-dl-ng may sanitize the filename
        if playlist_dir.exists():
            # Look for any file with target extension that matches the pattern
            # artist - title (accounting for filename sanitization)
            for existing_file in playlist_dir.glob(f"*{target_ext}"):
                # Basic match: check if artist and title appear in filename
                filename_lower = existing_file.stem.lower()
                artist_lower = track.artist.lower()
                title_lower = track.title.lower()

                # Check if both artist and title are in the filename
                # This handles cases where tidal-dl-ng sanitized characters
                if artist_lower in filename_lower and title_lower in filename_lower:
                    logger.debug(
                        f"Track {track.id} already exists as {existing_file}, "
                        "skipping"
                    )
                    return DecisionResult(
                        action=SyncAction.NO_ACTION,
                        track_id=track.id,
                        playlist_id=playlist.id,
                        playlist_track_id=playlist_track.id,
                        target_path=str(existing_file),
                        reason="File already exists at target location",
                        priority=0,
                    )

        return DecisionResult(
            action=SyncAction.DOWNLOAD_TRACK,
            track_id=track.id,
            playlist_id=playlist.id,
            playlist_track_id=playlist_track.id,
            target_path=str(target_path),
            reason="Track not yet downloaded",
            priority=10,
            metadata={
                "tidal_id": track.tidal_id,
                "title": track.title,
                "artist": track.artist,
            },
        )

    def _decide_symlink_action(
        self, playlist: Any, track: Track, playlist_track: Any
    ) -> DecisionResult:
        """Decide symlink action for a track in a playlist.

        Args:
            playlist: Playlist object
            track: Track object
            playlist_track: PlaylistTrack association object

        Returns:
            DecisionResult with symlink-related action
        """
        # Check if this playlist should have the primary file
        if playlist_track.is_primary:
            # This playlist has the primary file
            if playlist_track.symlink_path:
                # Shouldn't have symlink if it's primary
                return DecisionResult(
                    action=SyncAction.REMOVE_SYMLINK,
                    track_id=track.id,
                    playlist_id=playlist.id,
                    playlist_track_id=playlist_track.id,
                    source_path=playlist_track.symlink_path,
                    reason="Primary file shouldn't have symlink",
                    priority=3,
                )
            else:
                # All good - primary file, no symlink
                return DecisionResult(
                    action=SyncAction.NO_ACTION,
                    track_id=track.id,
                    playlist_id=playlist.id,
                    playlist_track_id=playlist_track.id,
                    reason="Primary file exists, no symlink needed",
                    priority=0,
                )

        # Not primary - should have symlink
        if not playlist_track.symlink_path:
            # Need to create symlink
            return self._decide_create_symlink(playlist, track, playlist_track)

        # Has symlink - check if valid
        if not playlist_track.symlink_valid:
            # Symlink is broken
            return DecisionResult(
                action=SyncAction.UPDATE_SYMLINK,
                track_id=track.id,
                playlist_id=playlist.id,
                playlist_track_id=playlist_track.id,
                source_path=playlist_track.symlink_path,
                target_path=track.file_path,
                reason="Symlink is broken, needs update",
                priority=7,
            )

        # Symlink exists and is valid
        return DecisionResult(
            action=SyncAction.NO_ACTION,
            track_id=track.id,
            playlist_id=playlist.id,
            playlist_track_id=playlist_track.id,
            reason="Symlink exists and is valid",
            priority=0,
        )

    def _decide_create_symlink(
        self, playlist: Any, track: Track, playlist_track: Any
    ) -> DecisionResult:
        """Decide to create a symlink.

        Args:
            playlist: Playlist object
            track: Track object
            playlist_track: PlaylistTrack association object

        Returns:
            DecisionResult with create symlink action
        """
        # Construct symlink path
        playlist_dir = self.playlists_root / playlist.name
        # Use same filename as primary file
        if track.file_path:
            filename = Path(track.file_path).name
        else:
            filename = (
                f"{track.normalized_name}.mp3"
                if track.normalized_name
                else f"{track.title}.mp3"
            )

        symlink_path = playlist_dir / filename

        return DecisionResult(
            action=SyncAction.CREATE_SYMLINK,
            track_id=track.id,
            playlist_id=playlist.id,
            playlist_track_id=playlist_track.id,
            source_path=str(symlink_path),
            target_path=track.file_path,
            reason="Track exists but playlist needs symlink",
            priority=6,
        )

    def get_prioritized_decisions(
        self, decisions: SyncDecisions
    ) -> List[DecisionResult]:
        """Get decisions sorted by priority (highest first).

        Args:
            decisions: SyncDecisions object

        Returns:
            List of DecisionResult sorted by priority
        """
        return sorted(decisions.decisions, key=lambda d: d.priority, reverse=True)

    def filter_decisions_by_action(
        self, decisions: SyncDecisions, action: SyncAction
    ) -> List[DecisionResult]:
        """Filter decisions by action type.

        Args:
            decisions: SyncDecisions object
            action: Action type to filter by

        Returns:
            List of DecisionResult matching the action
        """
        return [d for d in decisions.decisions if d.action == action]
