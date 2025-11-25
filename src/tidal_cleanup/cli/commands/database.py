"""Database-driven CLI commands for Tidal cleanup application.

This module contains the modern database-backed sync commands that provide state
tracking, conflict resolution, and deduplication.
"""

import logging
from collections import Counter
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ...config import Config
from ...core.filesystem import FilesystemScanner
from ...core.sync import DeduplicationLogic, SyncDecisionEngine, SyncOrchestrator
from ...core.tidal import TidalDownloadService, TidalStateFetcher
from ...database import (
    ConsoleProgressReporter,
    DatabaseService,
    TqdmProgressReporter,
)
from ...database.models import Playlist, PlaylistTrack, Track
from ..display import display_db_sync_result

console = Console()
logger = logging.getLogger(__name__)


def setup_progress_reporter(progress: bool, verbose: bool) -> None:
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


@click.group("db")
def db() -> None:
    """Database-driven sync commands (new architecture).

    These commands use the new database-backed sync system that provides:
    - State tracking across sync operations
    - Conflict detection and resolution
    - Progress tracking with visual feedback
    - Deduplication logic for symlink management
    """
    pass


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
    setup_progress_reporter(progress, verbose)

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
        display_db_sync_result(summary, dry_run)

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
