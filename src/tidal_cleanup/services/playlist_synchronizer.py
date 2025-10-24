"""Playlist synchronization service with object-oriented design."""

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table
from thefuzz import process

from tidal_cleanup.models.models import ComparisonResult

from .file_service import FileService
from .tidal_service import TidalConnectionError, TidalService
from .track_comparison_service import TrackComparisonService

console = Console()
logger = logging.getLogger(__name__)


class DeletionMode(Enum):
    """Modes for handling track deletion."""

    ASK = "ask"  # Ask user for each file (default)
    AUTO_DELETE = "auto_delete"  # Delete without asking
    AUTO_SKIP = "auto_skip"  # Skip deletion without asking


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
        deletion_mode: DeletionMode = DeletionMode.ASK,
    ):
        """Initialize playlist processor.

        Args:
            tidal_service: Service for Tidal API operations
            file_service: Service for file operations
            comparison_service: Service for track comparison
            config: Application configuration
            deletion_mode: Mode for handling track deletion
        """
        self.tidal_service = tidal_service
        self.file_service = file_service
        self.comparison_service = comparison_service
        self.config = config
        self.deletion_mode = deletion_mode

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
        tidal_track_names = {track.normalized_name for track in tidal_tracks}

        # Get local tracks with metadata from MP3 folder if it exists
        local_tracks_with_metadata = []
        local_track_names = set()
        mp3_folder = self.config.mp3_directory / "Playlists" / playlist.name
        if mp3_folder.exists():
            local_tracks_with_metadata = self.file_service.get_tracks_with_metadata(
                mp3_folder
            )
            # Use normalized names from MP3 tracks for comparison
            local_track_names = {
                track.normalized_name for track in local_tracks_with_metadata
            }
        else:
            # Fall back to M4A folder if MP3 folder doesn't exist
            local_track_names = self.file_service.get_track_names(m4a_folder)

        # Compare tracks
        comparison = self.comparison_service.compare_track_sets(
            local_track_names, tidal_track_names, playlist.name
        )

        # Display comparison results with detailed track info
        self._display_comparison_results(
            comparison, tidal_tracks, local_tracks_with_metadata
        )

        # Get tracks to delete
        tracks_to_delete = self.comparison_service.get_tracks_to_delete(comparison)

        # Determine which folder to operate on for deletions
        target_folder = mp3_folder if mp3_folder.exists() else m4a_folder

        # Handle track deletion outside of progress context if user input is needed
        if tracks_to_delete and self.deletion_mode == DeletionMode.ASK:
            # Pause progress for user input
            progress.stop()
            console.print()  # Add a blank line for better readability

            # Collect deletion decisions
            deletion_decisions = self._collect_deletion_decisions(
                target_folder, tracks_to_delete
            )

            # Resume progress
            progress.start()
            progress.update(task, description=f"Deleting files from {playlist.name}...")

            # Execute deletions
            self._execute_deletions(deletion_decisions)
        else:
            # For auto modes, just delete directly
            self._delete_tracks_auto(target_folder, tracks_to_delete)

        # Also process MP3 folder
        mp3_folder = self.config.mp3_directory / "Playlists" / playlist.name
        if mp3_folder.exists():
            self._sync_mp3_folder(m4a_folder, mp3_folder)

    def _display_comparison_results(
        self,
        comparison: ComparisonResult,
        tidal_tracks: Optional[List[Any]] = None,
        local_tracks: Optional[List[Any]] = None,
    ) -> None:
        """Display comparison results to console.

        Args:
            comparison: ComparisonResult object
            tidal_tracks: List of Track objects from Tidal (optional)
            local_tracks: List of Track objects from local files with metadata
        """
        # Display main comparison summary
        console.print(
            f"Comparison for '{comparison.playlist_name}': "
            f"{comparison.matched_count} matched, "
            f"{comparison.local_count} local only, "
            f"{comparison.tidal_count} tidal only"
        )

        # Create mappings for detailed info
        tidal_track_map = self._create_track_map(tidal_tracks)
        local_track_map = self._create_track_map(local_tracks)

        # Display local-only and tidal-only tracks
        self._display_local_only_tracks(comparison, local_track_map, local_tracks)
        self._display_tidal_only_tracks(comparison, tidal_track_map)

    def _create_track_map(self, tracks: Optional[List[Any]]) -> Dict[str, Any]:
        """Create a mapping from normalized track names to track objects.

        Args:
            tracks: List of track objects

        Returns:
            Dictionary mapping normalized names to track objects
        """
        track_map = {}
        if tracks:
            for track in tracks:
                track_map[track.normalized_name] = track
        return track_map

    def _display_local_only_tracks(
        self,
        comparison: ComparisonResult,
        local_track_map: Dict[str, Any],
        local_tracks: Optional[List[Any]],
    ) -> None:
        """Display local-only tracks table.

        Args:
            comparison: ComparisonResult object
            local_track_map: Map of normalized names to local track objects
            local_tracks: List of local track objects
        """
        if comparison.local_count == 0:
            return

        console.print()
        console.print(f"[yellow]Local-only tracks ({comparison.local_count}):[/yellow]")

        # Create detailed table for local tracks if metadata available
        local_table = Table(show_header=True, header_style="bold yellow")

        if local_tracks and local_track_map:
            self._add_detailed_columns(local_table)
            self._add_local_track_rows(
                local_table, comparison.local_only, local_track_map
            )
        else:
            # Use simple track name display if no metadata available
            local_table.add_column("Track Name", style="white")
            for track_name in sorted(comparison.local_only):
                local_table.add_row(track_name)

        console.print(local_table)

    def _display_tidal_only_tracks(
        self, comparison: ComparisonResult, tidal_track_map: Dict[str, Any]
    ) -> None:
        """Display tidal-only tracks table.

        Args:
            comparison: ComparisonResult object
            tidal_track_map: Map of normalized names to tidal track objects
        """
        if comparison.tidal_count == 0:
            return

        console.print()
        console.print(f"[cyan]Tidal-only tracks ({comparison.tidal_count}):[/cyan]")

        # Create detailed table for Tidal tracks
        tidal_table = Table(show_header=True, header_style="bold cyan")
        self._add_detailed_columns(tidal_table)
        self._add_tidal_track_rows(tidal_table, comparison.tidal_only, tidal_track_map)
        console.print(tidal_table)

    def _add_detailed_columns(self, table: Table) -> None:
        """Add detailed columns to a track table.

        Args:
            table: Table to add columns to
        """
        table.add_column("Title", style="white", no_wrap=False)
        table.add_column("Artist", style="green", no_wrap=False)
        table.add_column("Duration", style="blue", justify="center")
        table.add_column("Album", style="magenta", no_wrap=False)
        table.add_column("Year", style="yellow", justify="center")

    def _add_local_track_rows(
        self, table: Table, track_names: Set[str], track_map: Dict[str, Any]
    ) -> None:
        """Add local track rows to table.

        Args:
            table: Table to add rows to
            track_names: Set of track names to display
            track_map: Map of normalized names to track objects
        """
        for track_name in sorted(track_names):
            if track_name in track_map:
                track = track_map[track_name]
                table.add_row(
                    track.title,
                    track.artist,
                    track.duration_formatted if track.duration else "Unknown",
                    track.album or "Unknown",
                    str(track.year) if track.year else "Unknown",
                )
            else:
                # Fallback for tracks without detailed info
                table.add_row(track_name, "Unknown", "Unknown", "Unknown", "Unknown")

    def _add_tidal_track_rows(
        self, table: Table, track_names: Set[str], track_map: Dict[str, Any]
    ) -> None:
        """Add tidal track rows to table.

        Args:
            table: Table to add rows to
            track_names: Set of track names to display
            track_map: Map of normalized names to track objects
        """
        for track_name in sorted(track_names):
            if track_name in track_map:
                track = track_map[track_name]
                table.add_row(
                    track.title,
                    track.artist,
                    track.duration_formatted if track.duration else "Unknown",
                    track.album or "Unknown",
                    str(track.year) if track.year else "Unknown",
                )
            else:
                # Fallback for tracks without detailed info
                table.add_row(track_name, "Unknown", "Unknown", "Unknown", "Unknown")

    def _collect_deletion_decisions(
        self, folder: Path, tracks_to_delete: Set[str]
    ) -> List[Path]:
        """Collect user decisions about which files to delete.

        Args:
            folder: Folder containing tracks
            tracks_to_delete: Set of track names to delete

        Returns:
            List of file paths that should be deleted
        """
        files_to_delete = []

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
                        should_delete = click.confirm(
                            f"Delete '{file_path.name}' (not in Tidal playlist)?",
                            default=False,
                        )
                        if should_delete:
                            files_to_delete.append(file_path)
                        break

        return files_to_delete

    def _execute_deletions(self, files_to_delete: List[Path]) -> None:
        """Execute file deletions.

        Args:
            files_to_delete: List of file paths to delete
        """
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                console.print(f"[red]Deleted:[/red] {file_path.name}")
            except OSError as e:
                logger.error(f"Failed to delete {file_path}: {e}")
                console.print(f"[red]Error deleting {file_path.name}: {e}[/red]")

    def _delete_tracks_auto(self, folder: Path, tracks_to_delete: Set[str]) -> None:
        """Delete tracks automatically based on deletion mode.

        Args:
            folder: Folder containing tracks
            tracks_to_delete: Set of track names to delete
        """
        if not tracks_to_delete:
            return

        if self.deletion_mode == DeletionMode.AUTO_SKIP:
            console.print(
                f"[yellow]Skipping deletion of {len(tracks_to_delete)} tracks[/yellow]"
            )
            return

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
                        if self.deletion_mode == DeletionMode.AUTO_DELETE:
                            try:
                                file_path.unlink()
                                console.print(f"[red]Deleted:[/red] {file_path.name}")
                            except OSError as e:
                                logger.error(f"Failed to delete {file_path}: {e}")
                                console.print(
                                    f"[red]Error deleting {file_path.name}: {e}[/red]"
                                )
                        break

    def _should_delete_file(self, file_path: Path, progress: Any) -> bool:
        """Determine if a file should be deleted based on deletion mode.

        Args:
            file_path: Path to the file to potentially delete
            progress: Rich progress instance to pause during user input

        Returns:
            True if file should be deleted, False otherwise
        """
        if self.deletion_mode == DeletionMode.AUTO_DELETE:
            return True
        elif self.deletion_mode == DeletionMode.AUTO_SKIP:
            return False
        else:  # DeletionMode.ASK
            # Pause the progress display for user input
            progress.stop()
            try:
                result = click.confirm(
                    f"Delete '{file_path.name}' (not in Tidal playlist)?", default=False
                )
                return result
            finally:
                # Resume the progress display
                progress.start()

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
        deletion_mode: DeletionMode = DeletionMode.ASK,
    ):
        """Initialize playlist synchronizer.

        Args:
            tidal_service: Service for Tidal API operations
            file_service: Service for file operations
            comparison_service: Service for track comparison
            config: Application configuration
            deletion_mode: Mode for handling track deletion
        """
        self.tidal_service = tidal_service
        self.config = config
        self.deletion_mode = deletion_mode

        self.playlist_filter = PlaylistFilter()
        self.playlist_processor = PlaylistProcessor(
            tidal_service, file_service, comparison_service, config, deletion_mode
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
