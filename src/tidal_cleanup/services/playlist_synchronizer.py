"""Playlist synchronization service with object-oriented design."""

import logging
from pathlib import Path
from typing import Any, List, Optional, Set

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from thefuzz import process

from .file_service import FileService
from .tidal_service import TidalConnectionError, TidalService
from .track_comparison_service import TrackComparisonService

console = Console()
logger = logging.getLogger(__name__)


class PlaylistFilter:
    """Handles playlist filtering with fuzzy matching."""

    def __init__(self, fuzzy_threshold: int = 60):
        """Initialize playlist filter.

        Args:
            fuzzy_threshold: Minimum score for fuzzy matching (0-100)
        """
        self.fuzzy_threshold = fuzzy_threshold

    def find_matching_playlist(
        self, playlists: List[Any], target_name: str
    ) -> Optional[Any]:
        """Find the best matching playlist using fuzzy search.

        Args:
            playlists: List of playlist objects
            target_name: Target playlist name to match

        Returns:
            Best matching playlist or None if no good match found
        """
        if not playlists:
            return None

        playlist_names = [playlist.name for playlist in playlists]

        # Use fuzzy matching to find the best match
        best_match = process.extractOne(
            target_name, playlist_names, score_cutoff=self.fuzzy_threshold
        )

        if best_match:
            matched_name = best_match[0]
            score = best_match[1]

            # Find the playlist object with the matching name
            for playlist in playlists:
                if playlist.name == matched_name:
                    console.print(
                        f"[yellow]Found playlist match: '{matched_name}' "
                        f"(score: {score})[/yellow]"
                    )
                    return playlist

        return None


class PlaylistProcessor:
    """Handles processing of individual playlists."""

    def __init__(
        self,
        tidal_service: TidalService,
        file_service: FileService,
        comparison_service: TrackComparisonService,
        config: Any,
    ):
        """Initialize playlist processor.

        Args:
            tidal_service: Service for Tidal API operations
            file_service: Service for file operations
            comparison_service: Service for track comparison
            config: Application configuration
        """
        self.tidal_service = tidal_service
        self.file_service = file_service
        self.comparison_service = comparison_service
        self.config = config

    def process_playlist(self, playlist: Any, progress: Any, task: Any) -> None:
        """Process a single playlist.

        Args:
            playlist: Playlist object to process
            progress: Rich progress instance
            task: Progress task ID
        """
        progress.update(task, description=f"Processing {playlist.name}...")

        # Check if local folder exists
        m4a_folder = self.config.m4a_directory / "Playlists" / playlist.name
        if not m4a_folder.exists():
            logger.warning(f"Local folder not found for playlist: {playlist.name}")
            return

        # Get Tidal tracks
        tidal_tracks = self.tidal_service.get_playlist_tracks(playlist.tidal_id)

        # Get local tracks
        local_track_names = self.file_service.get_track_names(m4a_folder)
        tidal_track_names = {track.normalized_name for track in tidal_tracks}

        # Compare tracks
        comparison = self.comparison_service.compare_track_sets(
            local_track_names, tidal_track_names, playlist.name
        )

        # Get tracks to delete
        tracks_to_delete = self.comparison_service.get_tracks_to_delete(comparison)

        # Delete unmatched tracks
        self._delete_tracks(m4a_folder, tracks_to_delete)

        # Also process MP3 folder
        mp3_folder = self.config.mp3_directory / "Playlists" / playlist.name
        if mp3_folder.exists():
            self._sync_mp3_folder(m4a_folder, mp3_folder)

    def _delete_tracks(self, folder: Path, tracks_to_delete: Set[str]) -> None:
        """Delete tracks that are not in Tidal playlist.

        Args:
            folder: Folder containing tracks
            tracks_to_delete: Set of track names to delete
        """
        for track_name in tracks_to_delete:
            # Find matching files with fuzzy search
            match_result = self.comparison_service.find_best_match(
                track_name,
                [
                    f.stem
                    for f in folder.rglob("*")
                    if f.suffix.lower() in self.config.audio_extensions
                ],
            )

            if match_result:
                matched_file_stem, score = match_result
                # Find the actual file with this stem
                for file_path in folder.rglob("*"):
                    if (
                        file_path.stem == matched_file_stem
                        and file_path.suffix.lower() in self.config.audio_extensions
                    ):
                        try:
                            file_path.unlink()
                            logger.info(f"Deleted: {file_path}")
                        except OSError as e:
                            logger.error(f"Failed to delete {file_path}: {e}")
                        break

    def _sync_mp3_folder(self, m4a_folder: Path, mp3_folder: Path) -> None:
        """Synchronize MP3 folder with M4A folder.

        Args:
            m4a_folder: Source M4A folder
            mp3_folder: Target MP3 folder to sync
        """
        m4a_stems = {
            f.stem
            for f in m4a_folder.rglob("*")
            if f.suffix.lower() in self.config.audio_extensions
        }

        # Delete MP3 files that don't have corresponding M4A files
        for mp3_file in mp3_folder.rglob("*.mp3"):
            if mp3_file.stem not in m4a_stems:
                try:
                    mp3_file.unlink()
                    logger.info(f"Deleted MP3: {mp3_file}")
                except OSError as e:
                    logger.error(f"Failed to delete MP3 {mp3_file}: {e}")


class PlaylistSynchronizer:
    """Main playlist synchronization coordinator."""

    def __init__(
        self,
        tidal_service: TidalService,
        file_service: FileService,
        comparison_service: TrackComparisonService,
        config: Any,
    ):
        """Initialize playlist synchronizer.

        Args:
            tidal_service: Service for Tidal API operations
            file_service: Service for file operations
            comparison_service: Service for track comparison
            config: Application configuration
        """
        self.tidal_service = tidal_service
        self.config = config

        self.playlist_filter = PlaylistFilter()
        self.playlist_processor = PlaylistProcessor(
            tidal_service, file_service, comparison_service, config
        )

    def sync_playlists(self, playlist_filter: Optional[str] = None) -> bool:
        """Synchronize Tidal playlists with local files.

        Args:
            playlist_filter: Optional playlist name to filter by (uses fuzzy matching)

        Returns:
            True if successful, False otherwise
        """
        try:
            console.print("[bold blue]Starting playlist synchronization...[/bold blue]")

            # Connect to Tidal
            self._connect_to_tidal()

            # Get and filter playlists
            playlists = self._get_filtered_playlists(playlist_filter)
            if not playlists:
                return False

            # Process playlists
            processed_count = self._process_playlists(playlists)

            console.print(
                f"[green]✓[/green] Processed {processed_count}/"
                f"{len(playlists)} playlists"
            )
            return True

        except TidalConnectionError as e:
            console.print(f"[red]✗[/red] Tidal connection failed: {e}")
            return False
        except Exception as e:
            logger.exception("Playlist synchronization failed")
            console.print(f"[red]✗[/red] Synchronization failed: {e}")
            return False

    def _connect_to_tidal(self) -> None:
        """Connect to Tidal API."""
        with console.status("[bold green]Connecting to Tidal..."):
            self.tidal_service.connect()
        console.print("[green]✓[/green] Connected to Tidal")

    def _get_filtered_playlists(self, playlist_filter: Optional[str]) -> List[Any]:
        """Get playlists, optionally filtered by name.

        Args:
            playlist_filter: Optional playlist name filter

        Returns:
            List of playlists to process
        """
        # Get all playlists
        with console.status("[bold green]Fetching playlists..."):
            all_playlists = self.tidal_service.get_playlists()

        console.print(f"[green]✓[/green] Found {len(all_playlists)} playlists")

        # Filter playlists if requested
        if playlist_filter:
            matched_playlist = self.playlist_filter.find_matching_playlist(
                all_playlists, playlist_filter
            )
            if matched_playlist:
                playlists = [matched_playlist]
                console.print(
                    f"[blue]Filtering to single playlist: "
                    f"{matched_playlist.name}[/blue]"
                )
            else:
                console.print(
                    f"[red]✗[/red] No playlist found matching " f"'{playlist_filter}'"
                )
                return []
        else:
            playlists = all_playlists

        return playlists

    def _process_playlists(self, playlists: List[Any]) -> int:
        """Process all playlists.

        Args:
            playlists: List of playlists to process

        Returns:
            Number of successfully processed playlists
        """
        processed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            task = progress.add_task("Processing playlists...", total=len(playlists))

            for playlist in playlists:
                try:
                    self.playlist_processor.process_playlist(playlist, progress, task)
                    processed += 1
                except Exception as e:
                    logger.error(f"Failed to process playlist {playlist.name}: {e}")
                    console.print(
                        f"[red]✗[/red] Failed to process playlist: {playlist.name}"
                    )

                progress.advance(task)

        return processed
