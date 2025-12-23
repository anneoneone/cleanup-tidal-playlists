"""Track distribution analysis for understanding playlist overlap.

This module implements logic to analyze which playlists contain which tracks. Since we
now download each track to every playlist it appears in, this is mainly for reporting
and statistics.
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Dict, List

from ...database.service import DatabaseService

logger = logging.getLogger(__name__)


@dataclass
class TrackDistribution:
    """Information about which playlists contain a track."""

    track_id: int
    playlist_ids: List[int]
    playlist_names: List[str]
    num_playlists: int


@dataclass
class DeduplicationResult:
    """Result of track distribution analysis."""

    distributions: List[TrackDistribution] = dataclass_field(default_factory=list)
    tracks_analyzed: int = 0
    tracks_in_multiple_playlists: int = 0

    def add_distribution(self, distribution: TrackDistribution) -> None:
        """Add a distribution and update statistics."""
        self.distributions.append(distribution)
        self.tracks_analyzed += 1
        if distribution.num_playlists > 1:
            self.tracks_in_multiple_playlists += 1

    def get_summary(self) -> Dict[str, int]:
        """Get summary statistics."""
        return {
            "tracks_analyzed": self.tracks_analyzed,
            "tracks_in_multiple_playlists": self.tracks_in_multiple_playlists,
        }

    @property
    def decisions(self) -> List[TrackDistribution]:
        """Backward-compatible alias for legacy result attribute."""
        return self.distributions


class DeduplicationLogic:
    """Logic for analyzing track distribution across playlists.

    Since we now download tracks to each playlist, this class is mainly for reporting
    which tracks appear in multiple playlists.
    """

    def __init__(self, db_service: DatabaseService):
        """Initialize deduplication logic.

        Args:
            db_service: Database service instance
        """
        self.db_service = db_service

    def analyze_track_distribution(self, track_id: int) -> TrackDistribution:
        """Analyze which playlists contain a track.

        Args:
            track_id: Track database ID

        Returns:
            TrackDistribution with playlist information
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
        playlist_ids = []
        playlist_names = []
        for pt in playlist_tracks:
            playlist = self.db_service.get_playlist_by_id(pt.playlist_id)
            if playlist:
                playlist_ids.append(playlist.id)
                playlist_names.append(playlist.name)

        return TrackDistribution(
            track_id=track_id,
            playlist_ids=playlist_ids,
            playlist_names=playlist_names,
            num_playlists=len(playlist_ids),
        )

    def analyze_all_tracks(self) -> DeduplicationResult:
        """Analyze all tracks and determine which are in multiple playlists.

        Returns:
            DeduplicationResult with all distributions
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

                # Analyze this track
                distribution = self.analyze_track_distribution(track.id)
                result.add_distribution(distribution)

            except Exception as e:
                logger.error("Error analyzing track %s: %s", track.id, e)
                continue

        return result

    def get_playlists_for_track(self, track_id: int) -> List[int]:
        """Get playlist IDs that contain a track.

        Args:
            track_id: Track database ID

        Returns:
            List of playlist IDs
        """
        try:
            distribution = self.analyze_track_distribution(track_id)
            return distribution.playlist_ids
        except ValueError:
            return []
