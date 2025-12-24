"""Sync Decision Engine for comparing Tidal state vs Filesystem state.

This module implements the decision logic that determines what actions need to be taken
to synchronize playlists between Tidal and the filesystem.
"""

import logging
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from ...database.models import DownloadStatus, Playlist, PlaylistTrack, Track
from ...database.service import DatabaseService

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .deduplication import DeduplicationLogic

logger = logging.getLogger(__name__)


class SyncAction(str, Enum):
    """Actions that can be taken to synchronize tracks and playlists."""

    # Track-level actions
    DOWNLOAD_TRACK = "download_track"  # Download track from Tidal
    UPDATE_METADATA = "update_metadata"  # Update track metadata
    REMOVE_FILE = "remove_file"  # Remove file no longer in Tidal
    VERIFY_FILE = "verify_file"  # Verify file integrity

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
    files_to_remove: int = 0
    metadata_updates: int = 0
    no_action_needed: int = 0

    def add_decision(self, decision: DecisionResult) -> None:
        """Add a decision and update statistics."""
        self.decisions.append(decision)

        # Update statistics based on action
        if decision.action == SyncAction.DOWNLOAD_TRACK:
            self.tracks_to_download += 1
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

    SUPPORTED_EXTENSIONS: tuple[str, ...] = (".mp3", ".flac", ".m4a", ".wav")

    def __init__(
        self,
        db_service: DatabaseService,
        music_root: Path | str,
        target_format: Optional[str] = None,
        dedup_logic: Optional["DeduplicationLogic"] = None,
    ):
        """Initialize the decision engine.

        Args:
            db_service: Database service instance
            music_root: Root directory for music files (contains Playlists/)
            target_format: Desired audio format/extension for downloads (default mp3)
            dedup_logic: Optional deduplication logic instance for future use
        """
        self.db_service = db_service
        self.music_root = Path(music_root)
        self.playlists_root = self.music_root / "Playlists"
        normalized_format = (target_format or "mp3").lower().replace(".", "")
        self.target_format = normalized_format
        self.target_extension = f".{normalized_format}"
        self.dedup_logic = dedup_logic
        self._track_active_cache: Dict[int, bool] = {}
        self._all_tracks_cache: List[Track] | None = None
        self._simplified_track_names: Dict[int, str] = {}

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
        active_playlist_paths = self._collect_active_playlist_paths(
            playlist, playlist_tracks
        )

        for pt in playlist_tracks:
            track = pt.track
            if not track:
                logger.warning("Track not found for PlaylistTrack %s", pt.id)
                continue

            # Decide action for this track in this playlist
            decision = self._decide_playlist_track_action(
                playlist, track, pt, active_playlist_paths
            )
            decisions.add_decision(decision)

        orphan_decisions = self._identify_orphan_file_decisions(
            playlist, playlist_tracks, decisions, active_playlist_paths
        )
        for orphan_decision in orphan_decisions:
            decisions.add_decision(orphan_decision)

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

    def cleanup_deleted_local_files(self) -> int:
        """Clean up local tracks whose files no longer exist on disk.

        This should be called after Tidal sync but before Rekordbox sync,
        to ensure deleted local files are removed from the database.

        Returns:
            Number of tracks removed
        """
        removed_count = 0

        # Get all playlists
        playlists = self.db_service.get_all_playlists()

        for playlist in playlists:
            removed = self._cleanup_playlist_local_tracks(playlist)
            removed_count += removed

        if removed_count > 0:
            logger.info(
                "Local file cleanup complete: removed %d deleted tracks from database",
                removed_count,
            )

        return removed_count

    def _cleanup_playlist_local_tracks(self, playlist: Playlist) -> int:
        """Clean up local tracks for a single playlist.

        Args:
            playlist: Playlist object

        Returns:
            Number of tracks removed
        """
        playlist_dir = self.playlists_root / playlist.name
        removed_count = 0

        if not playlist_dir.exists():
            # Entire playlist directory missing - clean up local-only tracks
            logger.info(
                "Playlist directory missing: %s - cleaning up local tracks",
                playlist.name,
            )
            removed_count = self._remove_local_only_tracks(playlist)
            return removed_count

        # Playlist directory exists - check individual files
        disk_files = {str(fp) for fp in self._list_audio_files(playlist_dir)}
        playlist_tracks = self.db_service.get_playlist_track_associations(playlist.id)

        for pt in playlist_tracks:
            if not pt.in_local:
                continue

            if self._should_remove_local_track(pt, disk_files, playlist_dir):
                removed_count += self._remove_local_track(playlist, pt)

        return removed_count

    def _remove_local_only_tracks(self, playlist: Playlist) -> int:
        """Remove all local-only tracks from a playlist.

        Args:
            playlist: Playlist object

        Returns:
            Number of tracks removed
        """
        removed_count = 0
        playlist_tracks = self.db_service.get_playlist_track_associations(playlist.id)

        for pt in playlist_tracks:
            if pt.in_local and not pt.in_tidal:
                removed_count += self._remove_local_track(playlist, pt)

        return removed_count

    def _should_remove_local_track(
        self, pt: PlaylistTrack, disk_files: Set[str], playlist_dir: Path
    ) -> bool:
        """Check if a local track should be removed (file no longer exists).

        Args:
            pt: PlaylistTrack object
            disk_files: Set of file paths on disk (full paths as strings)
            playlist_dir: Path to the playlist directory

        Returns:
            True if track file doesn't exist on disk in this playlist
        """
        track = self.db_service.get_track_by_id(pt.track_id)
        if not track or not track.file_paths:
            return True  # No file paths - should remove

        # Check if any of the track's files exist in THIS playlist directory
        # file_paths contains relative paths from music_root
        for file_path_str in track.file_paths:
            # Build full path from relative path
            full_path = str(self.music_root / file_path_str)

            # Check if this file exists on disk
            if full_path in disk_files:
                return False  # File exists, don't remove

        # No files found in this playlist, so remove the track from this playlist
        return True

    def _remove_local_track(self, playlist: Playlist, pt: PlaylistTrack) -> int:
        """Remove a local track from a playlist.

        This removes the playlist-track association and cleans up file paths
        for this specific playlist from the track's file_paths array.

        Args:
            playlist: Playlist object
            pt: PlaylistTrack object

        Returns:
            1 if successful, 0 otherwise
        """
        logger.info(
            "Removing local track %s from playlist %s (file no longer on disk)",
            pt.track_id,
            playlist.name,
        )
        try:
            # First, clean up the file paths for this playlist
            track = self.db_service.get_track_by_id(pt.track_id)
            if track and track.file_paths:
                playlist_prefix = f"Playlists/{playlist.name}/"

                # Remove file paths that belong to this playlist
                updated_paths = [
                    fp for fp in track.file_paths if not fp.startswith(playlist_prefix)
                ]

                # Update track with cleaned file paths
                if updated_paths != track.file_paths:
                    self.db_service.update_track(
                        track.id,
                        {"file_paths": updated_paths},
                    )
                    logger.debug(
                        "Cleaned file_paths for track %s: removed %d paths from %s",
                        track.id,
                        len(track.file_paths) - len(updated_paths),
                        playlist.name,
                    )

            # Then remove the track from the playlist
            self.db_service.remove_track_from_playlist(
                playlist.id, pt.track_id, source="local"
            )
            return 1
        except Exception as e:
            logger.error(
                "Failed to remove local track %s from playlist %s: %s",
                pt.track_id,
                playlist.name,
                e,
            )
            return 0

    def _decide_playlist_track_action(
        self,
        playlist: Playlist,
        track: Track,
        playlist_track: PlaylistTrack,
        active_playlist_paths: Dict[str, Set[int]],
    ) -> DecisionResult:
        """Decide what action to take for a track in a playlist.

        Args:
            playlist: Playlist object
            track: Track object
            playlist_track: PlaylistTrack association object

        Returns:
            DecisionResult with the action to take
        """
        existing_path = self._find_existing_track_file(playlist, track)

        removal_decision = self._decide_removal_action(
            playlist, track, playlist_track, active_playlist_paths, existing_path
        )
        if removal_decision:
            return removal_decision

        if existing_path and existing_path.exists():
            return DecisionResult(
                action=SyncAction.NO_ACTION,
                track_id=track.id,
                playlist_id=playlist.id,
                playlist_track_id=playlist_track.id,
                target_path=str(existing_path),
                reason="Track exists in playlist directory",
                priority=0,
            )

        # Check if track needs to be downloaded to this playlist
        if track.download_status == DownloadStatus.NOT_DOWNLOADED:
            return self._decide_download_action(playlist, track, playlist_track)

        # Check if track is in error state - retry download
        if track.download_status == DownloadStatus.ERROR:
            decision = self._decide_download_action(playlist, track, playlist_track)
            # Update reason and priority for retry
            decision.reason = "Track download previously failed, retry needed"
            decision.priority = 5
            return decision

        # Track is downloaded, check if file exists in this playlist's directory
        decision = self._decide_download_action(playlist, track, playlist_track)
        decision.reason = "Track needs to be downloaded to this playlist"
        decision.priority = 6
        return decision

    def _decide_download_action(
        self, playlist: Playlist, track: Track, playlist_track: PlaylistTrack
    ) -> DecisionResult:
        """Decide download action for a track.

        Args:
            playlist: Playlist object
            track: Track object
            playlist_track: PlaylistTrack association object

        Returns:
            DecisionResult with download action or NO_ACTION if file exists
        """
        # Don't try to download local tracks - they already exist on disk
        # and have no tidal_id
        if playlist_track.in_local:
            logger.debug("Track %s is a local track, skipping download", track.id)
            return DecisionResult(
                action=SyncAction.NO_ACTION,
                track_id=track.id,
                playlist_id=playlist.id,
                playlist_track_id=playlist_track.id,
                reason="Local track - already exists on filesystem",
                priority=0,
            )

        # Skip tracks that are marked as unavailable in Tidal (404 errors)
        if track.tidal_unavailable:
            logger.debug(
                "Track %s is unavailable in Tidal, skipping download", track.id
            )
            return DecisionResult(
                action=SyncAction.NO_ACTION,
                track_id=track.id,
                playlist_id=playlist.id,
                playlist_track_id=playlist_track.id,
                reason="Track unavailable in Tidal (404)",
                priority=0,
            )

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

        target_path = self._build_track_path(playlist, track)

        # Check if file already exists at target location or elsewhere in dir
        existing_file = self._find_matching_playlist_file(playlist_dir, track)
        if existing_file is not None:
            logger.debug(
                "Track %s already exists as %s, skipping download",
                track.id,
                existing_file,
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

    def _decide_removal_action(
        self,
        playlist: Playlist,
        track: Track,
        playlist_track: PlaylistTrack,
        active_playlist_paths: Dict[str, Set[int]],
        existing_path: Optional[Path] = None,
    ) -> Optional[DecisionResult]:
        """Determine if a playlist-track should trigger a removal action.

        Don't remove files that:
        - Are still in Tidal (in_tidal=True)
        - Exist locally on filesystem (in_local=True)
        """
        if playlist_track.in_tidal:
            return None

        # Don't delete files that exist locally, even if removed from Tidal
        if playlist_track.in_local:
            logger.debug(
                "Skipping removal for track %s in playlist %s; "
                "file exists locally (in_local=True)",
                track.id,
                playlist.id,
            )
            return None

        # Check for an actual file associated with this playlist
        if existing_path is None:
            existing_path = self._find_existing_track_file(playlist, track)
        if not existing_path or not existing_path.exists():
            return None

        existing_path_key = str(existing_path)
        active_track_users = active_playlist_paths.get(existing_path_key, set())
        if active_track_users:
            logger.debug(
                "Skipping removal for %s in playlist %s; "
                "path reused by active track(s) %s",
                existing_path_key,
                playlist.id,
                sorted(active_track_users),
            )
            return None

        return DecisionResult(
            action=SyncAction.REMOVE_FILE,
            track_id=track.id,
            playlist_id=playlist.id,
            playlist_track_id=playlist_track.id,
            source_path=str(existing_path),
            reason="Track removed from playlist in Tidal",
            priority=8,
        )

    def _build_track_path(self, playlist: Playlist, track: Track) -> Path:
        """Compute the expected file location for a track within a playlist."""
        playlist_dir = self.playlists_root / playlist.name

        # Construct filename using artist - title format (matches tidal-dl-ng)
        if track.artist and track.title:
            base_filename = f"{track.artist} - {track.title}"
        elif track.title:
            base_filename = track.title
        else:
            base_filename = f"track-{track.id}"

        filename = f"{base_filename}{self.target_extension}"
        return playlist_dir / filename

    def _identify_orphan_file_decisions(
        self,
        playlist: Playlist,
        playlist_tracks: List[PlaylistTrack],
        decisions: SyncDecisions,
        active_playlist_paths: Dict[str, Set[int]],
    ) -> List[DecisionResult]:
        """Find files on disk that no longer belong to a Tidal playlist.

        Local tracks (marked with in_local=True) are preserved even if not in Tidal.
        """
        playlist_dir = self.playlists_root / playlist.name
        if not playlist_dir.exists():
            return []

        track_map: Dict[int, PlaylistTrack] = {
            pt.track_id: pt for pt in playlist_tracks if pt.track_id
        }
        existing_sources = {
            str(Path(d.source_path))
            for d in decisions.decisions
            if d.action == SyncAction.REMOVE_FILE and d.source_path
        }

        orphan_decisions: List[DecisionResult] = []
        for file_path in self._list_audio_files(playlist_dir):
            if str(file_path) in active_playlist_paths:
                continue
            if str(file_path) in existing_sources:
                continue

            track = self._find_track_for_path(file_path)
            playlist_track = track_map.get(track.id) if track else None

            # If track exists in playlist, skip it
            if playlist_track is not None:
                continue

            # File found locally but not in current Tidal playlist
            # Check if we already know about this file in the database for this playlist
            if track:
                # Track was matched to an existing database entry
                existing_local_pt = self._check_if_local_track(playlist.id, track.id)
                if existing_local_pt and existing_local_pt.in_local:
                    # Already marked as local - preserve it
                    logger.debug(
                        "Preserving local track %s (%s) in playlist %s",
                        track.id,
                        file_path.name,
                        playlist.name,
                    )
                    continue

            # File not in current Tidal playlist - create new local track entry
            # This is a locally-added file, not a Tidal track
            logger.info(
                "Found local file %s not in Tidal - creating new local track",
                file_path.name,
            )
            self._create_local_track(playlist.id, file_path)

        return orphan_decisions

    def _list_audio_files(self, playlist_dir: Path) -> List[Path]:
        """Return audio files in a playlist directory."""
        files: List[Path] = []
        for item in playlist_dir.iterdir():
            if item.is_file() and item.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                files.append(item)
        return sorted(files)

    def _find_existing_track_file(
        self, playlist: Playlist, track: Track
    ) -> Optional[Path]:
        """Locate an on-disk file for a playlist/track pair."""
        playlist_dir = self.playlists_root / playlist.name
        for raw_path in track.file_paths or []:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = self.music_root / raw_path
            if (
                candidate.parent == playlist_dir or playlist_dir in candidate.parents
            ) and candidate.exists():
                return candidate

        fallback = self._build_track_path(playlist, track)
        if fallback.exists():
            return fallback

        return None

    def _find_matching_playlist_file(
        self, playlist_dir: Path, track: Track
    ) -> Optional[Path]:
        """Find an existing file in the playlist directory for the track."""
        # 1) Prefer explicit file_paths stored on the track
        for raw_path in track.file_paths or []:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = self.music_root / raw_path
            if candidate.exists() and (
                candidate.parent == playlist_dir or playlist_dir in candidate.parents
            ):
                return candidate

        # 2) Try the expected target path (artist - title with target extension)
        if track.artist and track.title:
            base_filename = f"{track.artist} - {track.title}"
        elif track.title:
            base_filename = track.title
        else:
            base_filename = f"track-{track.id}"

        target_path = playlist_dir / f"{base_filename}{self.target_extension}"
        if target_path.exists():
            return target_path

        # 3) Fallback: case-insensitive stem match for same extension
        match = self._match_by_stem_case_insensitive(playlist_dir, base_filename)
        if match:
            return match

        # 4) Fuzzy match on simplified stems (handles artist/title tweaks)
        match = self._match_by_simplified_stem(playlist_dir, base_filename)
        if match:
            return match

        return None

    def _match_by_stem_case_insensitive(
        self, playlist_dir: Path, base_filename: str
    ) -> Optional[Path]:
        """Case-insensitive stem match within playlist dir for target extension."""
        target_stem = base_filename.lower()
        for existing_file in playlist_dir.glob(f"*{self.target_extension}"):
            if existing_file.stem.lower() == target_stem:
                return existing_file
        return None

    def _match_by_simplified_stem(
        self, playlist_dir: Path, base_filename: str
    ) -> Optional[Path]:
        """Fuzzy stem match using simplified names to tolerate metadata tweaks."""
        target_simple = self._simplify_name(base_filename.lower())
        for existing_file in self._list_audio_files(playlist_dir):
            if self._simplify_name(existing_file.stem) == target_simple:
                return existing_file
        return None

    def _collect_active_playlist_paths(
        self, playlist: Playlist, playlist_tracks: List[PlaylistTrack]
    ) -> Dict[str, Set[int]]:
        """Map playlist file paths that are still referenced in Tidal."""
        playlist_dir = self.playlists_root / playlist.name
        active_paths: Dict[str, Set[int]] = {}

        for pt in playlist_tracks:
            if not pt.in_tidal or not pt.track:
                continue
            for raw_path in pt.track.file_paths or []:
                candidate = Path(raw_path)
                if not candidate.is_absolute():
                    candidate = self.music_root / raw_path
                if not (
                    candidate.parent == playlist_dir
                    or playlist_dir in candidate.parents
                ):
                    continue
                if not candidate.exists():
                    continue
                active_paths.setdefault(str(candidate), set()).add(pt.track_id)

            # Fall back to locating the file within the playlist directory if
            # the track doesn't yet have an explicit file-path entry for this
            # playlist (common when tracks were re-added in Tidal before a new
            # filesystem scan).
            existing_path = self._find_existing_track_file(playlist, pt.track)
            if existing_path and existing_path.exists():
                active_paths.setdefault(str(existing_path), set()).add(pt.track_id)

        return active_paths

    def _find_track_for_path(self, file_path: Path) -> Optional[Track]:
        """Attempt to find the Track associated with a filesystem path."""
        relative_path = self._to_library_relative_path(file_path)
        track = self.db_service.get_track_by_path(relative_path)
        if track:
            return track
        return self._match_file_to_track(file_path)

    def _match_file_to_track(self, file_path: Path) -> Optional[Track]:
        """Match a file to a track by filename heuristics."""
        filename = file_path.stem
        artist_title = self._split_filename_artist_title(filename)
        if artist_title:
            track = self._match_by_normalized_name(*artist_title)
            if track:
                return track

        return self._match_by_similarity(filename)

    def _split_filename_artist_title(self, filename: str) -> Optional[tuple[str, str]]:
        """Split filenames formatted as 'Artist - Title'."""
        if " - " not in filename:
            return None
        artist, title = filename.split(" - ", 1)
        artist = artist.strip()
        title = title.strip()
        if not artist or not title:
            return None
        return artist, title

    def _match_by_normalized_name(self, artist: str, title: str) -> Optional[Track]:
        """Look up a track by its normalized artist/title combination."""
        normalized_name = f"{artist.lower()} - {title.lower()}"
        return self.db_service.find_track_by_normalized_name(normalized_name)

    def _match_by_similarity(self, filename: str) -> Optional[Track]:
        """Use fuzzy scoring to find the best matching track for a filename."""
        simplified_filename = self._simplify_name(filename.lower())
        best_candidate: Optional[Track] = None
        best_score = 0

        for candidate in self._get_all_tracks_cached():
            candidate_simple = self._get_simplified_track_name(candidate)
            if candidate_simple and candidate_simple == simplified_filename:
                return candidate

            score = self._compute_similarity_score(
                candidate, simplified_filename, candidate_simple
            )
            if score > best_score:
                best_score = score
                best_candidate = candidate

        return best_candidate

    def _compute_similarity_score(
        self,
        candidate: Track,
        simplified_filename: str,
        candidate_simple: Optional[str],
    ) -> int:
        """Return a heuristic score for how well a track matches a filename."""
        title_simple = self._simplify_name(
            candidate.title.lower() if candidate.title else ""
        )
        artist_simple = self._simplify_name(
            candidate.artist.lower() if candidate.artist else ""
        )

        title_match = bool(title_simple and title_simple in simplified_filename)
        artist_match = bool(artist_simple and artist_simple in simplified_filename)

        if not title_match and not artist_match:
            return 0

        score = 0
        if title_match:
            score += len(title_simple)
        if artist_match:
            score += len(artist_simple)
        if candidate_simple and candidate_simple in simplified_filename:
            score += len(candidate_simple)
        if candidate.duration:
            score += candidate.duration // 5

        return score

    def _simplify_name(self, value: Optional[str]) -> str:
        """Normalize a name for approximate comparisons.

        Keeps unicode letters (including accented chars like ü, ä, ö) but removes spaces
        and special characters to allow fuzzy matching.
        """
        if not value:
            return ""
        # Remove spaces and special chars but keep unicode letters
        # Use unicodedata.category() to identify letter characters
        simplified = "".join(
            ch for ch in value if unicodedata.category(ch)[0] == "L" or ch.isdigit()
        )
        return simplified

    def _get_simplified_track_name(self, track: Track) -> str:
        """Return cached simplified version of a track's normalized name."""
        track_id = track.id
        if track_id in self._simplified_track_names:
            return self._simplified_track_names[track_id]

        base_name = track.normalized_name
        if not base_name:
            parts: List[str] = []
            if track.artist:
                parts.append(track.artist.lower())
            if track.title:
                parts.append(track.title.lower())
            base_name = " - ".join(parts)

        simplified = self._simplify_name(base_name)
        self._simplified_track_names[track_id] = simplified
        return simplified

    def _check_if_local_track(
        self, playlist_id: int, track_id: int
    ) -> Optional[PlaylistTrack]:
        """Check if a track exists in the database for this playlist.

        Args:
            playlist_id: Playlist database ID
            track_id: Track database ID

        Returns:
            PlaylistTrack object if exists, None otherwise
        """
        try:
            playlist_tracks = self.db_service.get_playlist_track_associations(
                playlist_id
            )
            for pt in playlist_tracks:
                if pt.track_id == track_id:
                    return pt
            return None
        except Exception as e:
            logger.warning(
                "Error checking if track %s is local in playlist %s: %s",
                track_id,
                playlist_id,
                e,
            )
            return None

    def _create_local_track(self, playlist_id: int, file_path: Path) -> None:
        """Create a new local track from a file.

        Args:
            playlist_id: Playlist database ID
            file_path: Path to the local file
        """
        try:
            # Extract metadata from audio file
            relative_path = self._to_library_relative_path(file_path)
            track_data: Dict[str, Any] = {"file_paths": [relative_path]}

            # Try to extract metadata from audio tags
            self._extract_audio_metadata(file_path, track_data)

            # Fallback to filename if no title/artist from tags
            self._apply_filename_fallback(file_path, track_data)

            # Create a brand new track (don't match to existing tracks)
            # This ensures local files get their own track entries
            track = self.db_service.create_track(track_data)

            # Add to playlist marked as local
            self.db_service.add_track_to_playlist(playlist_id, track.id, in_local=True)

            logger.info(
                "Created local track '%s - %s' (ID: %s) from file %s",
                track_data.get("artist", "Unknown"),
                track_data.get("title", "Unknown"),
                track.id,
                file_path.name,
            )
        except Exception as e:
            logger.error(
                "Failed to create local track from file %s: %s", file_path.name, e
            )

    def _extract_audio_metadata(
        self, file_path: Path, track_data: Dict[str, Any]
    ) -> None:
        """Extract metadata from audio file tags.

        Args:
            file_path: Path to audio file
            track_data: Dictionary to populate with metadata
        """
        try:
            import mutagen

            audio = mutagen.File(file_path, easy=True)
            if not audio:
                return

            # Extract text metadata using helper
            self._extract_text_tags(audio, track_data)

            # Extract numeric metadata
            self._extract_numeric_tags(audio, track_data)

            logger.debug("Extracted metadata from %s: %s", file_path.name, track_data)
        except Exception as e:
            logger.warning("Failed to extract metadata from %s: %s", file_path, e)

    def _extract_text_tags(self, audio: Any, track_data: Dict[str, Any]) -> None:
        """Extract text tags from audio file.

        Args:
            audio: Mutagen audio object
            track_data: Dictionary to populate
        """
        tag_mappings = {
            "title": "title",
            "artist": "artist",
            "album": "album",
            "albumartist": "album_artist",
            "genre": "genre",
            "isrc": "isrc",
        }

        for audio_tag, db_field in tag_mappings.items():
            value = self._get_audio_tag(audio, audio_tag)
            if value:
                track_data[db_field] = value

    def _extract_numeric_tags(self, audio: Any, track_data: Dict[str, Any]) -> None:
        """Extract numeric tags (duration, year) from audio file.

        Args:
            audio: Mutagen audio object
            track_data: Dictionary to populate
        """
        from contextlib import suppress

        # Extract duration
        if hasattr(audio.info, "length"):
            track_data["duration"] = int(audio.info.length)

        # Extract year from date tag
        year_str = self._get_audio_tag(audio, "date")
        if year_str and len(year_str) >= 4:
            with suppress(ValueError):
                track_data["year"] = int(year_str[:4])

    def _apply_filename_fallback(
        self, file_path: Path, track_data: Dict[str, Any]
    ) -> None:
        """Apply filename-based fallback for missing metadata.

        Args:
            file_path: Path to audio file
            track_data: Dictionary to populate with metadata
        """
        if track_data.get("title") and track_data.get("artist"):
            return

        filename = file_path.stem
        artist_title = self._split_filename_artist_title(filename)

        if artist_title:
            artist, title = artist_title
            if not track_data.get("title"):
                track_data["title"] = title
            if not track_data.get("artist"):
                track_data["artist"] = artist
        else:
            if not track_data.get("title"):
                track_data["title"] = filename
            if not track_data.get("artist"):
                track_data["artist"] = "Unknown Artist"

    def _get_audio_tag(self, audio: Any, tag: str) -> Optional[str]:
        """Get tag value from audio file.

        Args:
            audio: Mutagen audio object
            tag: Tag name

        Returns:
            Tag value or None
        """
        if not (hasattr(audio, "tags") and audio.tags and tag in audio.tags):
            return None

        try:
            value = audio.tags[tag]
            if isinstance(value, list) and value:
                return str(value[0])
            return str(value)
        except Exception:
            return None

    def _to_library_relative_path(self, file_path: Path) -> str:
        """Return a path relative to the music library root when possible."""
        try:
            return str(file_path.relative_to(self.music_root))
        except ValueError:
            return str(file_path)

    def _get_all_tracks_cached(self) -> List[Track]:
        """Cache the list of tracks to avoid repeated full-table scans."""
        if self._all_tracks_cache is None:
            self._all_tracks_cache = self.db_service.get_all_tracks()
        return self._all_tracks_cache

    def _track_in_active_playlist(self, track_id: int) -> bool:
        """Check if track still belongs to at least one playlist in Tidal."""
        if track_id not in self._track_active_cache:
            active = self.db_service.track_has_active_playlist(track_id)
            self._track_active_cache[track_id] = active
        return self._track_active_cache[track_id]

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
