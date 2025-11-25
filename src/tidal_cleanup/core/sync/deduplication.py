"""Deduplication logic for determining primary file locations.

This module implements logic to decide which playlist should contain the primary
(actual) file for each track, while other playlists get symlinks. This avoids
downloading the same track multiple times.
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List

from ...database.service import DatabaseService

logger = logging.getLogger(__name__)


@dataclass
class PrimaryFileDecision:
    """Decision about which playlist should have the primary file for a track."""

    track_id: int
    primary_playlist_id: int
    primary_playlist_name: str
    symlink_playlist_ids: List[int]
    reason: str


@dataclass
class DeduplicationResult:
    """Result of deduplication analysis."""

    decisions: List[PrimaryFileDecision] = dataclass_field(default_factory=list)
    tracks_analyzed: int = 0
    tracks_with_primary: int = 0
    tracks_needing_primary: int = 0
    symlinks_needed: int = 0

    def add_decision(self, decision: PrimaryFileDecision) -> None:
        """Add a decision and update statistics."""
        self.decisions.append(decision)
        self.tracks_analyzed += 1
        self.symlinks_needed += len(decision.symlink_playlist_ids)

    def get_summary(self) -> Dict[str, int]:
        """Get summary statistics."""
        return {
            "tracks_analyzed": self.tracks_analyzed,
            "tracks_with_primary": self.tracks_with_primary,
            "tracks_needing_primary": self.tracks_needing_primary,
            "symlinks_needed": self.symlinks_needed,
        }


class DeduplicationLogic:
    """Logic for determining which playlist should have the primary file.

    When a track appears in multiple playlists, we need to decide which playlist gets
    the actual audio file and which get symlinks. This class implements various
    strategies for making that decision.
    """

    def __init__(
        self,
        db_service: DatabaseService,
        strategy: str = "first_alphabetically",
    ):
        """Initialize deduplication logic.

        Args:
            db_service: Database service instance
            strategy: Strategy for choosing primary playlist
                - 'first_alphabetically': Choose first playlist alphabetically
                - 'largest_playlist': Choose playlist with most tracks
                - 'prefer_existing': Prefer playlist that already has the file
        """
        self.db_service = db_service
        self.strategy = strategy

    def analyze_track_distribution(self, track_id: int) -> PrimaryFileDecision:
        """Analyze which playlists contain a track and decide primary location.

        Args:
            track_id: Track database ID

        Returns:
            PrimaryFileDecision with primary playlist and symlink locations
        """
        # Get all PlaylistTrack associations for this track
        from ...database.models import PlaylistTrack

        with self.db_service.get_session() as session:
            from sqlalchemy import select

            stmt = select(PlaylistTrack).where(PlaylistTrack.track_id == track_id)
            playlist_tracks = list(session.scalars(stmt).all())

        if not playlist_tracks:
            logger.warning("Track %d not in any playlists", track_id)
            raise ValueError(f"Track {track_id} not found in any playlists")

        # Get playlist information for each
        playlists = []
        for pt in playlist_tracks:
            playlist = self.db_service.get_playlist_by_id(pt.playlist_id)
            if playlist:
                playlists.append(
                    {
                        "id": playlist.id,
                        "name": playlist.name,
                        "playlist_track": pt,
                        "num_tracks": playlist.num_tracks or 0,
                    }
                )

        if not playlists:
            raise ValueError(f"Could not find playlists for track {track_id}")

        # Apply strategy to choose primary
        primary = self._choose_primary_playlist(playlists, track_id)

        # All other playlists get symlinks
        symlink_ids: List[int] = []
        for p in playlists:
            if p["id"] != primary["id"]:
                symlink_ids.append(p["id"])  # type: ignore[arg-type]

        return PrimaryFileDecision(
            track_id=track_id,
            primary_playlist_id=primary["id"],
            primary_playlist_name=primary["name"],
            symlink_playlist_ids=symlink_ids,
            reason=f"Selected by strategy: {self.strategy}",
        )

    def analyze_all_tracks(self) -> DeduplicationResult:
        """Analyze all tracks and determine primary file locations.

        Returns:
            DeduplicationResult with all decisions
        """
        result = DeduplicationResult()

        # Get all tracks
        tracks = self.db_service.get_all_tracks()

        for track in tracks:
            try:
                # Get PlaylistTrack associations for this track
                from ...database.models import PlaylistTrack

                with self.db_service.get_session() as session:
                    from sqlalchemy import select

                    stmt = select(PlaylistTrack).where(
                        PlaylistTrack.track_id == track.id
                    )
                    playlist_tracks = list(session.scalars(stmt).all())

                # Skip tracks not in any playlists
                if not playlist_tracks:
                    continue

                # Skip tracks in only one playlist (no deduplication needed)
                if len(playlist_tracks) == 1:
                    result.tracks_analyzed += 1
                    result.tracks_with_primary += 1
                    continue

                # Analyze this track
                decision = self.analyze_track_distribution(track.id)
                result.add_decision(decision)

                # Check if track already has primary
                has_primary = any(pt.is_primary for pt in playlist_tracks)
                if has_primary:
                    result.tracks_with_primary += 1
                else:
                    result.tracks_needing_primary += 1

            except Exception as e:
                logger.error("Error analyzing track %s: %s", track.id, e)
                continue

        return result

    def _choose_primary_playlist(
        self, playlists: List[Dict[str, Any]], track_id: int
    ) -> Dict[str, Any]:
        """Choose which playlist should have the primary file.

        Args:
            playlists: List of playlist info dicts
            track_id: Track ID being analyzed

        Returns:
            Playlist dict that should have the primary file
        """
        if self.strategy == "first_alphabetically":
            return self._strategy_first_alphabetically(playlists)
        elif self.strategy == "largest_playlist":
            return self._strategy_largest_playlist(playlists)
        elif self.strategy == "prefer_existing":
            return self._strategy_prefer_existing(playlists, track_id)
        else:
            logger.warning(
                f"Unknown strategy '{self.strategy}', using first_alphabetically"
            )
            return self._strategy_first_alphabetically(playlists)

    def _strategy_first_alphabetically(
        self, playlists: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Choose first playlist alphabetically by name."""
        return sorted(playlists, key=lambda p: p["name"].lower())[0]

    def _strategy_largest_playlist(
        self, playlists: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Choose playlist with most tracks."""
        return max(playlists, key=lambda p: p["num_tracks"])

    def _strategy_prefer_existing(
        self, playlists: List[Dict[str, Any]], track_id: int
    ) -> Dict[str, Any]:
        """Prefer playlist that already has is_primary=True, else alphabetically."""
        # Check if any playlist already marked as primary
        for playlist in playlists:
            if playlist["playlist_track"].is_primary:
                return playlist

        # If none marked as primary, check if file exists in any
        track = self.db_service.get_track_by_id(track_id)
        if track and track.file_path and Path(track.file_path).exists():
            # File exists - try to find which playlist directory it's in
            file_path = Path(track.file_path)
            for playlist in playlists:
                # Check if file path contains playlist name
                if playlist["name"] in str(file_path):
                    return playlist

        # Fall back to alphabetical
        return self._strategy_first_alphabetically(playlists)

    def get_primary_playlist_for_track(self, track_id: int) -> int | None:
        """Get the playlist ID that should have the primary file for a track.

        Args:
            track_id: Track database ID

        Returns:
            Playlist ID that should have primary file, or None if track not found
        """
        try:
            decision = self.analyze_track_distribution(track_id)
            return decision.primary_playlist_id
        except ValueError:
            return None

    def should_be_primary(self, track_id: int, playlist_id: int) -> bool:
        """Check if a playlist should have the primary file for a track.

        Args:
            track_id: Track database ID
            playlist_id: Playlist database ID

        Returns:
            True if this playlist should have the primary file
        """
        primary_playlist_id = self.get_primary_playlist_for_track(track_id)
        return primary_playlist_id == playlist_id

    def get_symlink_playlists_for_track(self, track_id: int) -> List[int]:
        """Get playlist IDs that should have symlinks for a track.

        Args:
            track_id: Track database ID

        Returns:
            List of playlist IDs that should have symlinks
        """
        try:
            decision = self.analyze_track_distribution(track_id)
            return decision.symlink_playlist_ids
        except ValueError:
            return []
