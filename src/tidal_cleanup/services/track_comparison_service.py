"""Track comparison service with fuzzy matching and normalization."""

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from thefuzz import process

from ..models.models import ComparisonResult, Track

logger = logging.getLogger(__name__)


class TrackComparisonService:
    """Service for comparing and matching tracks between sources."""

    def __init__(self, fuzzy_threshold: int = 80):
        """Initialize track comparison service.

        Args:
            fuzzy_threshold: Minimum score for fuzzy matching (0-100)
        """
        self.fuzzy_threshold = fuzzy_threshold

    def normalize_track_name(self, track_name: str) -> str:
        """Normalize track name for comparison.

        This method:
        - Removes additional artists after comma or "feat."
        - Removes remix/edit/mix terms
        - Removes content in brackets and parentheses
        - Removes years
        - Removes trailing dots
        - Normalizes whitespace and converts to lowercase

        Args:
            track_name: Original track name

        Returns:
            Normalized track name
        """
        # Split into artist and title if possible
        parts = track_name.split(" - ", maxsplit=1)
        if len(parts) == 2:
            artist, title = parts

            # Clean artist name (remove additional artists)
            artist = (
                re.sub(r"(,| feat\.| & ).*", "", artist, flags=re.IGNORECASE)
                .strip()
                .lower()
            )

            # Remove trailing dots from artist
            artist = re.sub(r"\.+$", "", artist)

            # Clean title
            title = self._clean_title(title)

            return f"{artist} - {title}"

        # If no artist-title separation, just clean the whole string
        return self._clean_title(track_name)

    def _clean_title(self, title: str) -> str:
        """Clean title part of track name.

        Args:
            title: Original title

        Returns:
            Cleaned title
        """
        # Remove content in brackets and parentheses
        title = re.sub(r"\[.*?\]|\(.*?\)", "", title, flags=re.IGNORECASE)

        # Remove years
        title = re.sub(r"\b\d{4}\b", "", title)

        # Remove remix/edit/mix terms
        title = re.sub(r"(remix|edit|mix|version)", "", title, flags=re.IGNORECASE)

        # Remove trailing dots
        title = re.sub(r"\.+$", "", title)

        # Normalize whitespace and convert to lowercase
        title = re.sub(r"\s+", " ", title).strip().lower()

        return title

    def compare_track_sets(
        self,
        local_tracks: Set[str],
        tidal_tracks: Set[str],
        playlist_name: str = "Unknown",
    ) -> ComparisonResult:
        """Compare two sets of track names.

        Args:
            local_tracks: Set of local track names
            tidal_tracks: Set of Tidal track names
            playlist_name: Name of playlist for result

        Returns:
            ComparisonResult object with comparison details
        """
        # Normalize track names
        normalized_local = {self.normalize_track_name(track) for track in local_tracks}
        normalized_tidal = {self.normalize_track_name(track) for track in tidal_tracks}

        # Find matches and differences
        matched = normalized_local & normalized_tidal
        local_only = normalized_local - normalized_tidal
        tidal_only = normalized_tidal - normalized_local

        result = ComparisonResult(
            playlist_name=playlist_name,
            local_only=local_only,
            tidal_only=tidal_only,
            matched=matched,
        )

        return result

    def find_best_match(
        self, target: str, candidates: List[str], threshold: Optional[int] = None
    ) -> Optional[Tuple[str, int]]:
        """Find best fuzzy match for a target string.

        Args:
            target: String to find match for
            candidates: List of candidate strings
            threshold: Minimum matching score (uses instance default if None)

        Returns:
            Tuple of (best_match, score) if found, None otherwise
        """
        if not candidates:
            return None

        threshold = threshold or self.fuzzy_threshold

        try:
            # Normalize target and candidates
            normalized_target = self.normalize_track_name(target)
            normalized_candidates = [
                self.normalize_track_name(candidate) for candidate in candidates
            ]

            # Find best match using fuzzy matching
            result = process.extractOne(normalized_target, normalized_candidates)

            if result and result[1] >= threshold:
                # Return original candidate string, not normalized
                best_match_index = normalized_candidates.index(result[0])
                original_match = candidates[best_match_index]
                return (original_match, result[1])

        except Exception as e:
            logger.warning("Fuzzy matching failed for '%s': %s", target, e)

        return None

    def find_fuzzy_matches(
        self,
        unmatched_tracks: Set[str],
        candidate_tracks: Set[str],
        threshold: Optional[int] = None,
    ) -> Dict[str, Tuple[str, int]]:
        """Find fuzzy matches for unmatched tracks.

        Args:
            unmatched_tracks: Set of tracks to find matches for
            candidate_tracks: Set of candidate tracks to match against
            threshold: Minimum matching score

        Returns:
            Dictionary mapping unmatched track to (match, score)
        """
        threshold = threshold or self.fuzzy_threshold
        candidates_list = list(candidate_tracks)

        fuzzy_matches = {}

        for track in unmatched_tracks:
            match_result = self.find_best_match(track, candidates_list, threshold)
            if match_result:
                fuzzy_matches[track] = match_result

        logger.info("Found %d fuzzy matches", len(fuzzy_matches))
        return fuzzy_matches

    def compare_playlists(
        self,
        local_playlist: List[Track],
        tidal_playlist: List[Track],
        playlist_name: str = "Unknown",
    ) -> ComparisonResult:
        """Compare local and Tidal playlist tracks.

        Args:
            local_playlist: List of local Track objects
            tidal_playlist: List of Tidal Track objects
            playlist_name: Name of playlist

        Returns:
            ComparisonResult object
        """
        local_names = {track.normalized_name for track in local_playlist}
        tidal_names = {track.normalized_name for track in tidal_playlist}

        return self.compare_track_sets(local_names, tidal_names, playlist_name)

    def get_tracks_to_delete(
        self, comparison_result: ComparisonResult, use_fuzzy_matching: bool = True
    ) -> Set[str]:
        """Get tracks that should be deleted (local only tracks).

        Args:
            comparison_result: Result from track comparison
            use_fuzzy_matching: Whether to use fuzzy matching to reduce deletions

        Returns:
            Set of track names that should be deleted
        """
        tracks_to_delete = comparison_result.local_only.copy()

        if use_fuzzy_matching and comparison_result.tidal_only:
            # Try to find fuzzy matches to reduce false deletions
            fuzzy_matches = self.find_fuzzy_matches(
                tracks_to_delete, comparison_result.tidal_only
            )

            # Remove tracks that have fuzzy matches
            for track in fuzzy_matches:
                tracks_to_delete.discard(track)
                logger.info(
                    f"Fuzzy match found: '{track}' -> "
                    f"'{fuzzy_matches[track][0]}' "
                    f"(score: {fuzzy_matches[track][1]})"
                )

        logger.info("Marked %d tracks for deletion", len(tracks_to_delete))
        return tracks_to_delete

    def validate_track_name(self, track_name: str) -> bool:
        """Validate if track name is in expected format.

        Args:
            track_name: Track name to validate

        Returns:
            True if track name appears to be in "Artist - Title" format
        """
        return " - " in track_name and len(track_name.split(" - ")) >= 2
