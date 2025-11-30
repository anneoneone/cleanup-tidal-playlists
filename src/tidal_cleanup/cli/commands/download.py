"""Download command for Tidal cleanup application.

This module contains the download command that bridges the legacy and database systems
to fetch tracks from Tidal and convert them to the target format.
"""

import logging
from typing import Any, Optional

import click
from rich.console import Console

from ...config import Config
from ...core.sync import (
    DownloadOrchestrator,
    SyncAction,
    SyncDecisionEngine,
    SyncDecisions,
)
from ...core.tidal import TidalApiService, TidalDownloadService, TidalStateFetcher
from ...database import DatabaseService
from ..display import display_download_results, filter_decisions_by_playlist
from .legacy import TidalCleanupApp

console = Console()
logger = logging.getLogger(__name__)


def fetch_tidal_playlists(
    db_service: DatabaseService,
    tidal_service: TidalApiService,
    download_service: TidalDownloadService,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch playlists from Tidal and return statistics.

    Args:
        db_service: Database service instance
        tidal_service: Tidal API service
        download_service: Download service for later use
        force: If True, fetch all tracks ignoring last update timestamps
        dry_run: If True, skip creating snapshots

    Returns:
        Dictionary with fetch statistics
    """
    # Connect to Tidal API
    with console.status("[bold green]Connecting to Tidal API..."):
        tidal_service.connect()
    console.print("[green]✓[/green] Connected to Tidal API")

    # Also connect download service for later use
    with console.status("[bold green]Initializing download service..."):
        download_service.connect()

    # Fetch playlists
    status_msg = "[bold green]Fetching playlists from Tidal..."
    if force:
        status_msg += " (forced - ignoring timestamps)"
    if dry_run:
        status_msg += " (no snapshot)"
    status_msg += "[/bold green]"

    with console.status(status_msg):
        fetcher = TidalStateFetcher(
            db_service,
            tidal_session=tidal_service.session,
            force=force,
            dry_run=dry_run,
        )
        _ = fetcher.fetch_all_playlists()
        stats = fetcher.get_fetch_statistics()

    console.print(
        f"[green]✓[/green] Fetched {stats.get('playlists_fetched', 0)} "
        f"playlists with {stats.get('tracks_created', 0)} new tracks"
    )
    return stats


@click.command("download")
@click.option(
    "-p",
    "--playlist",
    type=str,
    default=None,
    help="Download only the specified playlist",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be downloaded without actually downloading",
)
@click.option(
    "--skip-fetch",
    is_flag=True,
    help="Skip fetching from Tidal (use existing database)",
)
@click.option(
    "--target-format",
    type=str,
    default="mp3",
    help="Target format for conversion (default: mp3)",
)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Force fetch all tracks, ignoring last update timestamps",
)
@click.pass_obj
def download(
    app: TidalCleanupApp,
    playlist: Optional[str],
    dry_run: bool,
    skip_fetch: bool,
    target_format: str,
    force: bool,
) -> None:
    """Download tracks from Tidal and convert to target format.

    This command uses the new database-driven sync system to:
    1. Fetch playlist metadata from Tidal (optional)
    2. Determine which tracks need to be downloaded
    3. Download missing tracks to the MP3 directory
    4. Convert downloaded files to target format (default: mp3)

    Examples:
        # Download all playlists and convert to MP3
        tidal-cleanup download

        # Download specific playlist and convert to MP3
        tidal-cleanup download -p "My Playlist"

        # Download and convert to FLAC
        tidal-cleanup download --target-format flac

        # Force fetch all tracks (ignore last update timestamps)
        tidal-cleanup download --force

        # Dry run to see what would be downloaded
        tidal-cleanup download --dry-run

        # Use existing database without fetching from Tidal
        tidal-cleanup download --skip-fetch
    """
    config = Config()
    db_service = DatabaseService(db_path=config.database_path)

    # Ensure database schema is initialized
    db_service.init_db()

    download_service = app.download_service
    tidal_service = app.tidal_service

    console.print("\n[bold cyan]📥 Database-driven download[/bold cyan]")
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No downloads will be performed[/yellow]")
        console.print(
            "[yellow]Note: Database will be updated to calculate diff between "
            "Tidal and local[/yellow]"
        )
    if force:
        console.print("[cyan]FORCE MODE - Ignoring last update timestamps[/cyan]")
    console.print()

    try:
        # Step 1: Fetch from Tidal (unless explicitly skipped)
        if not skip_fetch:
            _ = fetch_tidal_playlists(
                db_service,
                tidal_service,
                download_service,
                force=force,
                dry_run=dry_run,
            )

        # Step 2: Determine target directory based on format
        target_format_normalized = target_format.lower().replace(".", "")
        if target_format_normalized == "mp3":
            target_root = config.mp3_directory
        else:
            target_root = config.mp3_directory.parent / target_format_normalized

        # Step 3: Generate sync decisions
        with console.status("[bold green]Analyzing what needs to be downloaded..."):
            decision_engine = SyncDecisionEngine(db_service, music_root=target_root)
            decisions = decision_engine.analyze_all_playlists()

        # Filter for download decisions only
        download_decisions = [
            d for d in decisions.decisions if d.action == SyncAction.DOWNLOAD_TRACK
        ]

        logger.info(
            "Generated %d total decisions, %d are download decisions",
            len(decisions.decisions),
            len(download_decisions),
        )

        # Filter by playlist if specified
        if playlist:
            download_decisions = filter_decisions_by_playlist(
                db_service, download_decisions, playlist
            )
            if not download_decisions:
                return

        if not download_decisions:
            console.print("[green]✓[/green] All tracks already downloaded!")
            return

        console.print(
            f"[cyan]Found {len(download_decisions)} track(s) to download[/cyan]\n"
        )

        # Step 4: Execute downloads and conversions
        orchestrator = DownloadOrchestrator(
            db_service=db_service,
            music_root=target_root,
            download_service=download_service,
            dry_run=dry_run,
        )

        download_only = SyncDecisions(decisions=download_decisions)

        with console.status(
            f"[bold green]Downloading and converting to {target_format.upper()}..."
        ):
            result = orchestrator.execute_decisions(
                download_only, target_format=target_format
            )

        # Step 5: Display results
        display_download_results(result)

    except Exception as e:
        logger.exception("Download failed")
        console.print(f"\n[red]✗ Download failed: {e}[/red]")
        raise click.ClickException(str(e))
