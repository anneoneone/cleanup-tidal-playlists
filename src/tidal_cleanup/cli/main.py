"""Command-line interface for the Tidal cleanup application."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.table import Table

from tidal_cleanup.models.models import ConversionJob

from ..config import Config, get_config
from ..database import (
    ConsoleProgressReporter,
    DatabaseService,
    SyncOrchestrator,
    TqdmProgressReporter,
)
from ..services import (
    DeletionMode,
    FileService,
    PlaylistSynchronizer,
    RekordboxGenerationError,
    RekordboxService,
    TidalDownloadError,
    TidalDownloadService,
    TidalService,
    TrackComparisonService,
)
from ..utils.logging_config import configure_third_party_loggers, setup_logging

console = Console()
logger = logging.getLogger(__name__)


class TidalCleanupApp:
    """Main application class."""

    def __init__(self, config_override: Optional[dict[str, Any]] = None) -> None:
        """Initialize application.

        Args:
            config_override: Optional configuration overrides
        """
        self.config = get_config()
        if config_override:
            for key, value in config_override.items():
                setattr(self.config, key, value)

        # Initialize services
        self.tidal_service = TidalService(self.config.tidal_token_file)
        self.file_service = FileService(self.config.audio_extensions)
        self.comparison_service = TrackComparisonService(
            self.config.fuzzy_match_threshold
        )
        self.rekordbox_service = RekordboxService()

        # Initialize playlist synchronizer
        self.playlist_synchronizer = PlaylistSynchronizer(
            self.tidal_service,
            self.file_service,
            self.comparison_service,
            self.config,
        )

        # Initialize download service
        self.download_service = TidalDownloadService(self.config)

    def sync_playlists(
        self,
        playlist_filter: Optional[str] = None,
        deletion_mode: DeletionMode = DeletionMode.ASK,
    ) -> bool:
        """Synchronize Tidal playlists with local files.

        Args:
            playlist_filter: Optional playlist name to filter by (uses fuzzy matching)
            deletion_mode: Mode for handling track deletion

        Returns:
            True if successful, False otherwise
        """
        # Create a new synchronizer with the specified deletion mode
        synchronizer = PlaylistSynchronizer(
            self.tidal_service,
            self.file_service,
            self.comparison_service,
            self.config,
            deletion_mode,
        )
        return synchronizer.sync_playlists(playlist_filter)

    def _download_tracks(self, playlist_name: Optional[str] = None) -> None:
        """Download tracks from Tidal to M4A directory.

        Args:
            playlist_name: Optional playlist name to download. If provided,
                          only that playlist will be downloaded.
        """
        try:
            # Connect to Tidal
            with console.status("[bold green]Connecting to Tidal..."):
                self.download_service.connect()
            console.print("[green]✓[/green] Connected to Tidal")

            if playlist_name:
                console.print(
                    f"[bold blue]Downloading playlist: {playlist_name}...[/bold blue]"
                )
                playlist_dir = self.download_service.download_playlist(playlist_name)
                console.print(
                    f"[green]✓[/green] Downloaded playlist to: {playlist_dir}"
                )
            else:
                console.print("[bold blue]Downloading all playlists...[/bold blue]")
                playlist_dirs = self.download_service.download_all_playlists()
                console.print(
                    f"[green]✓[/green] Downloaded {len(playlist_dirs)} playlists"
                )

        except TidalDownloadError as e:
            console.print(f"[red]✗[/red] Download failed: {e}")
            raise click.ClickException(str(e))
        except Exception as e:
            logger.exception("Download failed")
            console.print(f"[red]✗[/red] Download failed: {e}")
            raise click.ClickException(str(e))

    # @convert convert
    def _convert_files(self, playlist_name: Optional[str] = None) -> None:
        """Convert M4A files to MP3.

        Args:
            playlist_name: Optional playlist name to convert. If provided,
                          only the closest matching playlist will be converted.
        """
        if playlist_name:
            console.print(
                f"[bold blue]Converting playlist: {playlist_name}...[/bold blue]"
            )
        else:
            console.print("[bold blue]Converting audio files...[/bold blue]")

        playlist_jobs = self.file_service.convert_directory(
            self.config.m4a_directory,
            self.config.mp3_directory,
            target_format=".mp3",
            quality=self.config.ffmpeg_quality,
            playlist_filter=playlist_name,
        )

        if not playlist_jobs:
            if playlist_name:
                console.print(
                    f"[yellow]No playlist found matching '{playlist_name}'[/yellow]"
                )
            else:
                console.print("[yellow]No playlists found to convert[/yellow]")
            return

        self.show_result_table(playlist_jobs)

    def generate_rekordbox_xml(self) -> bool:
        """Generate Rekordbox XML file.

        Returns:
            True if successful, False otherwise
        """
        try:
            console.print("[bold blue]Generating Rekordbox XML...[/bold blue]")

            if not self.rekordbox_service.validate_input_folder(
                self.config.rekordbox_input_folder
            ):
                console.print(
                    "[red]✗[/red] Invalid input folder for Rekordbox generation"
                )
                return False

            track_count = self.rekordbox_service.get_track_count_estimate(
                self.config.rekordbox_input_folder
            )

            with console.status(f"[bold green]Processing ~{track_count} tracks..."):
                self.rekordbox_service.generate_xml(
                    self.config.rekordbox_input_folder,
                    self.config.rekordbox_output_file,
                )

            console.print(
                f"[green]✓[/green] Rekordbox XML generated: "
                f"{self.config.rekordbox_output_file}"
            )
            return True

        except RekordboxGenerationError as e:
            console.print(f"[red]✗[/red] Rekordbox generation failed: {e}")
            return False
        except Exception as e:
            logger.exception("Rekordbox XML generation failed")
            console.print(f"[red]✗[/red] Rekordbox generation failed: {e}")
            return False

    def show_result_table(self, playlist_jobs: dict[str, List[ConversionJob]]) -> None:
        """Show result of playlist conversion."""
        total_converted = 0
        total_skipped = 0
        total_deleted = 0
        total_failed = 0

        console.print("\nConversion complete:")

        # Collect all stats first
        playlist_stats = {}
        for playlist_name, jobs in playlist_jobs.items():
            converted = len(
                [j for j in jobs if j.status == "completed" and not j.was_skipped]
            )
            skipped = len([j for j in jobs if j.was_skipped])
            deleted = len([j for j in jobs if j.status == "deleted"])
            failed = len([j for j in jobs if j.status == "failed"])

            playlist_stats[playlist_name] = {
                "converted": converted,
                "skipped": skipped,
                "deleted": deleted,
                "failed": failed,
            }

            total_converted += converted
            total_skipped += skipped
            total_deleted += deleted
            total_failed += failed

        # Create a table for proper alignment
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Playlist", style="bold white", no_wrap=True)
        table.add_column("Converted", style="green", justify="right")
        table.add_column("", style="none")  # "converted" text
        table.add_column("Skipped", style="yellow", justify="right")
        table.add_column("", style="none")  # "skipped" text
        table.add_column("Deleted", style="red", justify="right")
        table.add_column("", style="none")  # "deleted" text
        table.add_column("Failed", style="red", justify="right")
        table.add_column("", style="none")  # "failed" text

        # Add playlist rows
        for playlist_name, stats in playlist_stats.items():
            table.add_row(
                playlist_name,
                str(stats["converted"]),
                "converted",
                str(stats["skipped"]),
                "skipped",
                str(stats["deleted"]),
                "deleted",
                str(stats["failed"]),
                "failed",
            )

        # Add overall summary row
        table.add_row("", "", "", "", "", "", "", "", "")  # Empty row for spacing
        table.add_row(
            "[bold cyan]Overall Summary[/bold cyan]",
            f"[green]{total_converted}[/green]",
            "converted",
            f"[yellow]{total_skipped}[/yellow]",
            "skipped",
            f"[red]{total_deleted}[/red]",
            "deleted",
            f"[red]{total_failed}[/red]",
            "failed",
        )

        console.print(table)

    def show_status(self) -> None:
        """Show application status and configuration."""
        table = Table(title="Tidal Cleanup Configuration")

        table.add_column("Setting", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        table.add_row("M4A Directory", str(self.config.m4a_directory))
        table.add_row("MP3 Directory", str(self.config.mp3_directory))
        table.add_row("Token File", str(self.config.tidal_token_file))
        table.add_row("Rekordbox Input", str(self.config.rekordbox_input_folder))
        table.add_row("Rekordbox Output", str(self.config.rekordbox_output_file))
        table.add_row("Fuzzy Threshold", str(self.config.fuzzy_match_threshold))
        table.add_row("Interactive Mode", str(self.config.interactive_mode))

        console.print(table)


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Set logging level",
)
@click.option("--log-file", type=click.Path(), help="Log to file")
@click.option("--no-interactive", is_flag=True, help="Disable interactive mode")
@click.pass_context
def cli(ctx: Any, log_level: str, log_file: str, no_interactive: bool) -> None:
    """Tidal Playlist Cleanup Tool.

    A modern tool for synchronizing Tidal playlists with local audio files.
    """
    # Set up logging
    setup_logging(log_level=log_level, log_file=Path(log_file) if log_file else None)
    configure_third_party_loggers()

    # Create app instance
    config_override = {}
    if no_interactive:
        config_override["interactive_mode"] = False

    app = TidalCleanupApp(config_override)
    ctx.obj = app


@cli.command()
@click.option(
    "--playlist",
    "-p",
    help="Sync only a specific playlist (exact folder name in MP3 directory)",
)
@click.option(
    "--emoji-config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to emoji-to-MyTag mapping config (uses default if not specified)",
)
@click.pass_obj
def _sync_all_playlists(
    rekordbox_service: RekordboxService,
    playlists_dir: Path,
    emoji_config: Optional[Path],
) -> None:
    """Sync all playlists in the playlists directory."""
    console.print("\n[bold cyan]🎵 Syncing all playlists to Rekordbox[/bold cyan]")
    console.print("=" * 60)

    if not playlists_dir.exists():
        console.print(f"[red]❌ Playlists directory not found: {playlists_dir}[/red]")
        raise click.Abort()

    # Get all playlist folders
    playlist_folders = [d for d in playlists_dir.iterdir() if d.is_dir()]

    if not playlist_folders:
        console.print("[yellow]⚠️ No playlist folders found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(playlist_folders)} playlists[/bold]\n")

    # Pre-create all genre/party folders
    console.print("[cyan]📁 Creating genre/party folders...[/cyan]")
    rekordbox_service.ensure_genre_party_folders(emoji_config_path=emoji_config)
    console.print("[green]✓ Folders ready[/green]\n")

    results = []
    for playlist_folder in sorted(playlist_folders):
        playlist_name = playlist_folder.name
        console.print(f"\n[cyan]Syncing: {playlist_name}[/cyan]")

        try:
            result = rekordbox_service.sync_playlist_with_mytags(
                playlist_name, emoji_config_path=emoji_config
            )
            results.append(result)
            _display_sync_result(result, compact=True)
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            logger.error(f"Failed to sync playlist {playlist_name}: {e}")

    # Display summary
    _display_batch_summary(results)


def _display_batch_summary(results: List[Dict[str, Any]]) -> None:
    """Display summary of batch sync operation."""
    console.print("\n[bold green]📊 Sync Summary[/bold green]")
    console.print("=" * 60)

    total_added = sum(r["tracks_added"] for r in results)
    total_removed = sum(r["tracks_removed"] for r in results)
    deleted_count = sum(1 for r in results if r.get("playlist_deleted"))

    summary_table = Table(show_header=False)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green", justify="right")

    summary_table.add_row("Total Playlists", str(len(results)))
    summary_table.add_row("Total Tracks Added", str(total_added))
    summary_table.add_row("Total Tracks Removed", str(total_removed))
    if deleted_count > 0:
        summary_table.add_row(
            "Playlists Deleted (empty)",
            f"[yellow]{deleted_count}[/yellow]",
        )

    console.print(summary_table)
    console.print()


def sync(
    app: TidalCleanupApp,
    playlist: Optional[str],
    emoji_config: Optional[Path],
) -> None:
    """Synchronize MP3 playlists to Rekordbox with emoji-based MyTag management.

    By default, syncs ALL playlists found in your MP3 Playlists folder.
    Use --playlist to sync only a specific playlist.

    Playlist Name Pattern: "NAME [GENRE/PARTY-EMOJI] [ENERGY-EMOJI] [STATUS-EMOJI]"

    Examples:
      - "House Italo R 🇮🇹❓" → Genre: House Italo, Status: Recherche
      - "Jazz D 🎷💾" → Genre: Jazz, Status: Archived

    Features:
      - Adds/removes tracks based on MP3 folder contents
      - Applies MyTags from emoji patterns in playlist names
      - Handles tracks in multiple playlists (accumulates tags)
      - Removes playlist-specific tags when tracks are removed
      - Deletes empty playlists automatically
    """
    try:
        rekordbox_service = RekordboxService(app.config)

        if playlist:
            # Sync single playlist
            console.print(f"\n[bold cyan]🎵 Syncing playlist: {playlist}[/bold cyan]")
            console.print("=" * 60)

            result = rekordbox_service.sync_playlist_with_mytags(
                playlist, emoji_config_path=emoji_config
            )
            _display_sync_result(result)
        else:
            # Sync all playlists
            playlists_dir = app.config.mp3_directory / "Playlists"
            _sync_all_playlists(rekordbox_service, playlists_dir, emoji_config)

    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        raise click.Abort()
    except Exception as e:
        logger.error(f"❌ Error syncing: {e}")
        import traceback

        traceback.print_exc()
        raise click.Abort()


def _display_sync_result(result: dict[str, Any], compact: bool = False) -> None:
    """Display sync results."""
    if compact:
        # Compact display for batch sync
        status = "✅"
        if result.get("playlist_deleted"):
            status = "⚠️ (deleted)"

        console.print(
            f"  {status} Added: {result['tracks_added']}, "
            f"Removed: {result['tracks_removed']}, "
            f"Final: {result['final_track_count']} tracks"
        )
    else:
        # Full display for single sync
        console.print("\n[bold green]✅ Sync completed successfully![/bold green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="green", justify="right")

        table.add_row("Playlist Name", result["playlist_name"])
        table.add_row("MP3 Tracks", str(result["mp3_tracks_count"]))
        table.add_row("Tracks Before", str(result["rekordbox_tracks_before"]))
        table.add_row("Tracks Added", str(result["tracks_added"]))
        table.add_row("Tracks Removed", str(result["tracks_removed"]))

        if result.get("playlist_deleted"):
            table.add_row("Status", "[yellow]⚠️ Playlist deleted (empty)[/yellow]")
            table.add_row("Final Track Count", "0")
        else:
            table.add_row("Final Track Count", str(result["final_track_count"]))

        console.print(table)
        console.print()


@cli.command()
@click.option(
    "-p",
    "--playlist",
    type=str,
    default=None,
    help="Download only the specified playlist",
)
@click.pass_obj
def download(app: TidalCleanupApp, playlist: Optional[str]) -> None:
    """Download tracks from Tidal to M4A directory."""
    app._download_tracks(playlist_name=playlist)


@cli.command()
@click.option(
    "-p",
    "--playlist",
    type=str,
    default=None,
    help="Convert only the playlist with closest match to the given name",
)
@click.pass_obj
def convert(app: TidalCleanupApp, playlist: Optional[str]) -> None:
    """Convert audio files from M4A to MP3."""
    app._convert_files(playlist_name=playlist)


@cli.command()
@click.pass_obj
def rekordbox(app: TidalCleanupApp) -> None:
    """Generate Rekordbox XML file."""
    success = app.generate_rekordbox_xml()
    if not success:
        raise click.ClickException("Rekordbox XML generation failed")


@cli.command()
@click.pass_obj
def status(app: TidalCleanupApp) -> None:
    """Show configuration and status."""
    app.show_status()


@cli.command()
@click.pass_obj
def full(app: TidalCleanupApp) -> None:
    """Run full workflow: sync, convert, and generate Rekordbox XML."""
    console.print("[bold green]Running full workflow...[/bold green]")

    # Sync playlists
    if not app.sync_playlists():
        raise click.ClickException("Synchronization failed")

    # Generate Rekordbox XML
    if not app.generate_rekordbox_xml():
        raise click.ClickException("Rekordbox XML generation failed")

    console.print("[bold green]✓ Full workflow completed successfully![/bold green]")


# ============================================================================
# Database-driven sync commands
# ============================================================================


@cli.group()
def db() -> None:
    """Database-driven sync commands (new architecture).

    These commands use the new database-backed sync system that provides:
    - State tracking across sync operations
    - Conflict detection and resolution
    - Progress tracking with visual feedback
    - Deduplication logic for symlink management
    """
    pass


def _setup_progress_reporter(progress: bool, verbose: bool) -> None:
    """Setup progress reporter (for future use).

    Args:
        progress: Whether to use progress bars
        verbose: Whether to show verbose output

    Note:
        Currently returns None as orchestrator doesn't support progress callbacks yet.
    """
    _ = None
    if progress:
        try:
            _ = TqdmProgressReporter()
        except ImportError:
            console.print("[yellow]tqdm not available, using console reporter[/yellow]")
            _ = ConsoleProgressReporter(verbose=verbose)
    elif verbose:
        _ = ConsoleProgressReporter(verbose=True)
    return None


@db.command(name="sync")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
@click.option(
    "--no-fetch",
    is_flag=True,
    help="Skip fetching state from Tidal (use existing database)",
)
@click.option(
    "--no-scan",
    is_flag=True,
    help="Skip scanning filesystem (use existing database)",
)
@click.option(
    "--no-dedup",
    is_flag=True,
    help="Skip deduplication analysis",
)
@click.option(
    "--progress/--no-progress",
    default=True,
    help="Show progress bars (requires tqdm)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed progress information",
)
def db_sync(
    dry_run: bool,
    no_fetch: bool,
    no_scan: bool,
    no_dedup: bool,
    progress: bool,
    verbose: bool,
) -> None:
    """Execute database-driven sync operation.

    This command orchestrates a complete sync:
    1. Fetch current state from Tidal API
    2. Scan local filesystem for existing files
    3. Analyze deduplication needs (symlink planning)
    4. Generate sync decisions (download, create symlinks, etc.)
    5. Execute decisions with conflict resolution

    Examples:
        # Full sync with progress
        tidal-cleanup db sync

        # Dry run to see what would happen
        tidal-cleanup db sync --dry-run

        # Sync without re-fetching Tidal data
        tidal-cleanup db sync --no-fetch

        # Sync with detailed progress
        tidal-cleanup db sync --verbose
    """
    config = Config()
    db_service = DatabaseService(db_path=config.database_path)
    download_service = TidalDownloadService(config)

    # Setup progress tracking (for future use)
    _setup_progress_reporter(progress, verbose)

    # Create orchestrator
    orchestrator = SyncOrchestrator(
        config=config,
        db_service=db_service,
        download_service=download_service,
        dry_run=dry_run,
    )

    # Execute sync
    console.print("\n[bold cyan]🔄 Starting database-driven sync...[/bold cyan]")
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")

    try:
        result = orchestrator.sync_all(
            fetch_tidal=not no_fetch,
            scan_filesystem=not no_scan,
            analyze_deduplication=not no_dedup,
        )

        # Display results
        summary = result.get_summary()
        _display_db_sync_result(summary, dry_run)

        if result.errors:
            console.print(f"\n[red]⚠️  {len(result.errors)} error(s) occurred:[/red]")
            for error in result.errors[:10]:  # Show first 10 errors
                console.print(f"  • {error}")
            if len(result.errors) > 10:
                console.print(f"  ... and {len(result.errors) - 10} more")

    except Exception as e:
        logger.exception("Sync failed")
        console.print(f"\n[red]✗ Sync failed: {e}[/red]")
        raise click.ClickException(str(e))


@db.command(name="fetch")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed information",
)
def db_fetch(verbose: bool) -> None:
    """Fetch current state from Tidal API.

    Downloads playlist and track metadata from Tidal and stores it in the database.
    This is typically the first step in a sync operation.

    Examples:
        tidal-cleanup db fetch
        tidal-cleanup db fetch -v
    """
    config = Config()
    db_service = DatabaseService(db_path=config.database_path)

    from ..database import TidalStateFetcher

    console.print("\n[bold cyan]📥 Fetching state from Tidal...[/bold cyan]\n")

    try:
        fetcher = TidalStateFetcher(db_service)
        _ = fetcher.fetch_all_playlists()
        stats = fetcher.get_fetch_statistics()

        console.print("[green]✓ Tidal state fetched successfully[/green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("Playlists Fetched", str(stats.get("playlists_fetched", 0)))
        table.add_row("Tracks Created", str(stats.get("tracks_created", 0)))
        table.add_row("Tracks Updated", str(stats.get("tracks_updated", 0)))
        table.add_row(
            "Playlist Tracks Created", str(stats.get("playlist_tracks_created", 0))
        )
        table.add_row(
            "Playlist Tracks Deleted", str(stats.get("playlist_tracks_deleted", 0))
        )

        console.print(table)

        if verbose and stats.get("errors"):
            errors = stats.get("errors", [])
            console.print(f"\n[yellow]Errors: {len(errors)}[/yellow]")
            for error in errors[:5]:
                console.print(f"  • {error}")

    except Exception as e:
        logger.exception("Fetch failed")
        console.print(f"\n[red]✗ Fetch failed: {e}[/red]")
        raise click.ClickException(str(e))


@db.command(name="scan")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed information",
)
def db_scan(verbose: bool) -> None:
    """Scan local filesystem for audio files.

    Scans the playlists directory and stores file metadata in the database.
    This discovers what files already exist locally.

    Examples:
        tidal-cleanup db scan
        tidal-cleanup db scan -v
    """
    config = Config()
    db_service = DatabaseService(db_path=config.database_path)

    from ..database import FilesystemScanner

    playlists_root = Path(config.m4a_directory) / "Playlists"

    console.print(
        f"\n[bold cyan]📂 Scanning filesystem: {playlists_root}[/bold cyan]\n"
    )

    try:
        scanner = FilesystemScanner(db_service, playlists_root=playlists_root)
        stats = scanner.scan_all_playlists()

        console.print("[green]✓ Filesystem scanned successfully[/green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("Playlists Scanned", str(stats.get("playlists_scanned", 0)))
        table.add_row("Files Found", str(stats.get("files_found", 0)))
        table.add_row("Symlinks Found", str(stats.get("symlinks_found", 0)))
        table.add_row("Broken Symlinks", str(stats.get("broken_symlinks", 0)))
        table.add_row("Files Removed", str(stats.get("files_removed", 0)))

        console.print(table)

        if verbose and stats.get("errors"):
            errors = stats.get("errors", [])
            console.print(f"\n[yellow]Errors: {len(errors)}[/yellow]")
            for error in errors[:5]:
                console.print(f"  • {error}")

    except Exception as e:
        logger.exception("Scan failed")
        console.print(f"\n[red]✗ Scan failed: {e}[/red]")
        raise click.ClickException(str(e))


@db.command(name="analyze")
@click.option(
    "--strategy",
    type=click.Choice(["first_alphabetically", "most_playlists", "newest_file"]),
    default="first_alphabetically",
    help="Deduplication strategy to use",
)
def db_analyze(strategy: str) -> None:
    """Analyze deduplication needs.

    Determines which files should be primary copies and which should be symlinks.
    This helps avoid duplicate downloads and saves disk space.

    Strategies:
        first_alphabetically: Use file from first playlist alphabetically
        most_playlists: Use file from playlist with most tracks
        newest_file: Use the newest file found

    Examples:
        tidal-cleanup db analyze
        tidal-cleanup db analyze --strategy most_playlists
    """
    config = Config()
    db_service = DatabaseService(db_path=config.database_path)

    from ..database import DeduplicationLogic

    console.print(
        f"\n[bold cyan]🔍 Analyzing deduplication "
        f"(strategy: {strategy})...[/bold cyan]\n"
    )

    try:
        dedup = DeduplicationLogic(db_service, strategy=strategy)
        result = dedup.analyze_all_tracks()

        console.print("[green]✓ Analysis complete[/green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        tracks_analyzed = len(result.decisions)
        total_symlinks = sum(len(d.symlink_playlist_ids) for d in result.decisions)
        tracks_needing_symlinks = sum(
            1 for d in result.decisions if len(d.symlink_playlist_ids) > 0
        )

        table.add_row("Tracks Analyzed", str(tracks_analyzed))
        table.add_row("Tracks Needing Symlinks", str(tracks_needing_symlinks))
        table.add_row("Total Symlinks Needed", str(total_symlinks))

        console.print(table)

    except Exception as e:
        logger.exception("Analysis failed")
        console.print(f"\n[red]✗ Analysis failed: {e}[/red]")
        raise click.ClickException(str(e))


@db.command(name="decisions")
@click.option(
    "--limit",
    type=int,
    default=20,
    help="Number of decisions to display",
)
@click.option(
    "--action",
    type=click.Choice(
        ["DOWNLOAD_TRACK", "CREATE_SYMLINK", "UPDATE_SYMLINK", "REMOVE_FILE", "ALL"]
    ),
    default="ALL",
    help="Filter by action type",
)
def db_decisions(limit: int, action: str) -> None:
    """Show sync decisions that would be executed.

    Displays what actions the sync system has decided to take, such as
    downloading tracks, creating symlinks, or removing files.

    Examples:
        tidal-cleanup db decisions
        tidal-cleanup db decisions --action DOWNLOAD_TRACK --limit 50
    """
    config = Config()
    db_service = DatabaseService(db_path=config.database_path)

    from ..database import SyncDecisionEngine

    console.print("\n[bold cyan]📋 Generating sync decisions...[/bold cyan]\n")

    try:
        engine = SyncDecisionEngine(db_service, music_root=config.m4a_directory)
        decisions = engine.analyze_all_playlists()

        # Filter by action if specified
        filtered_decisions = decisions.decisions
        if action != "ALL":
            filtered_decisions = [
                d for d in decisions.decisions if d.action.name == action
            ]

        console.print(
            f"[green]✓ Generated {len(decisions.decisions)} decisions[/green]"
        )
        if action != "ALL":
            console.print(
                f"[cyan]Showing {len(filtered_decisions)} "
                f"decisions of type {action}[/cyan]\n"
            )
        else:
            console.print()

        # Display decisions
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Action", style="cyan", no_wrap=True)
        table.add_column("Track ID", style="white")
        table.add_column("Details", style="yellow")

        for decision in filtered_decisions[:limit]:
            track_id = str(decision.track_id) if decision.track_id else "N/A"

            details = decision.reason or ""
            if decision.target_path:
                details = str(decision.target_path)

            table.add_row(decision.action.value, track_id, details)

        console.print(table)

        if len(filtered_decisions) > limit:
            console.print(
                f"\n[dim]... and {len(filtered_decisions) - limit} more decisions[/dim]"
            )

        # Summary by action type
        summary_table = Table(
            show_header=True, header_style="bold magenta", title="\nSummary by Action"
        )
        summary_table.add_column("Action", style="cyan")
        summary_table.add_column("Count", style="green", justify="right")

        from collections import Counter

        action_counts = Counter(d.action.name for d in decisions.decisions)
        for action_name, count in sorted(action_counts.items()):
            summary_table.add_row(action_name, str(count))

        console.print(summary_table)

    except Exception as e:
        logger.exception("Decision generation failed")
        console.print(f"\n[red]✗ Failed to generate decisions: {e}[/red]")
        raise click.ClickException(str(e))


@db.command(name="status")
def db_status() -> None:
    """Show database sync system status.

    Displays current state of the database including track counts,
    playlist information, and file system state.

    Examples:
        tidal-cleanup db status
    """
    config = Config()
    db_service = DatabaseService(db_path=config.database_path)

    console.print("\n[bold cyan]📊 Database Status[/bold cyan]\n")

    try:
        # Ensure database tables exist
        db_service.init_db()

        # Get statistics from database
        with db_service.get_session() as session:
            from ..database.models import Playlist, PlaylistTrack, Track

            track_count = session.query(Track).count()
            playlist_count = session.query(Playlist).count()
            playlist_track_count = session.query(PlaylistTrack).count()
            # Count tracks with file paths (files on disk)
            file_count = (
                session.query(Track).filter(Track.file_path.isnot(None)).count()
            )

        # Display database info
        db_table = Table(show_header=False, box=None)
        db_table.add_column("Setting", style="cyan", no_wrap=True)
        db_table.add_column("Value", style="white")

        db_table.add_row("Database Path", str(config.database_path))
        db_table.add_row("M4A Directory", str(config.m4a_directory))
        db_table.add_row("Playlists Directory", str(config.m4a_directory / "Playlists"))

        console.print(db_table)
        console.print()

        # Display counts
        count_table = Table(show_header=True, header_style="bold magenta")
        count_table.add_column("Entity", style="cyan")
        count_table.add_column("Count", style="green", justify="right")

        count_table.add_row("Total Tracks", str(track_count))
        count_table.add_row("Total Playlists", str(playlist_count))
        count_table.add_row("Playlist-Track Associations", str(playlist_track_count))
        count_table.add_row("Tracks with Files", str(file_count))

        console.print(count_table)

    except Exception as e:
        logger.exception("Status check failed")
        console.print(f"\n[red]✗ Status check failed: {e}[/red]")
        raise click.ClickException(str(e))


def _display_db_sync_result(summary: dict[str, Any], dry_run: bool) -> None:
    """Display database sync results."""
    console.print("\n[bold green]✓ Sync operation completed[/bold green]\n")

    if "tidal" in summary:
        table = Table(
            show_header=True, header_style="bold magenta", title="Tidal Fetch"
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        tidal = summary["tidal"]
        table.add_row("Playlists Fetched", str(tidal["playlists_fetched"]))
        table.add_row("Tracks Created", str(tidal["tracks_created"]))
        table.add_row("Tracks Updated", str(tidal["tracks_updated"]))

        console.print(table)
        console.print()

    if "filesystem" in summary:
        table = Table(
            show_header=True, header_style="bold magenta", title="Filesystem Scan"
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        fs = summary["filesystem"]
        table.add_row("Playlists Scanned", str(fs["playlists_scanned"]))
        table.add_row("Files Found", str(fs["files_found"]))

        console.print(table)
        console.print()

    if "deduplication" in summary:
        table = Table(
            show_header=True, header_style="bold magenta", title="Deduplication"
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        dedup = summary["deduplication"]
        table.add_row("Tracks Analyzed", str(dedup["tracks_analyzed"]))
        table.add_row("Symlinks Needed", str(dedup["symlinks_needed"]))

        console.print(table)
        console.print()

    if "decisions" in summary:
        table = Table(
            show_header=True, header_style="bold magenta", title="Decisions Generated"
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        decisions = summary["decisions"]
        table.add_row("Total Decisions", str(decisions["total"]))
        table.add_row("Downloads", str(decisions["downloads"]))
        table.add_row("Symlinks", str(decisions["symlinks"]))

        console.print(table)
        console.print()

    if "execution" in summary and not dry_run:
        table = Table(
            show_header=True, header_style="bold magenta", title="Execution Results"
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        execution = summary["execution"]
        table.add_row("Decisions Executed", str(execution["decisions_executed"]))
        table.add_row("Downloads Attempted", str(execution["downloads_attempted"]))
        table.add_row("Downloads Successful", str(execution["downloads_successful"]))
        table.add_row("Downloads Failed", str(execution["downloads_failed"]))
        table.add_row("Symlinks Created", str(execution["symlinks_created"]))
        table.add_row("Symlinks Updated", str(execution["symlinks_updated"]))

        console.print(table)


if __name__ == "__main__":
    cli()
