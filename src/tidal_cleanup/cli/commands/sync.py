"""Unified sync command that runs both Tidal and Rekordbox sync."""

import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from ...config import Config
from ...core.rekordbox.snapshot_service import RekordboxSnapshotService
from ...core.tidal.snapshot_service import TidalSnapshotService
from .init import init_db, init_rekordbox, init_tidal_api

console = Console()
logger = logging.getLogger(__name__)


@click.command("sync")
@click.option(
    "--playlist",
    "-p",
    help="Sync only a specific playlist (by name)",
)
@click.option(
    "--emoji-config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to emoji-to-MyTag mapping config for Rekordbox folder placement",
)
@click.option(
    "--skip-tidal",
    is_flag=True,
    help="Skip Tidal sync (only sync to Rekordbox)",
)
@click.option(
    "--skip-rekordbox",
    is_flag=True,
    help="Skip Rekordbox sync (only sync from Tidal)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
def sync_command(
    playlist: Optional[str],
    emoji_config: Optional[Path],
    skip_tidal: bool,
    skip_rekordbox: bool,
    dry_run: bool,
) -> None:
    """Unified sync: Tidal → Database → Rekordbox.

    This command performs a complete sync workflow:
    1. Sync Tidal playlists to local database
    2. Sync database playlists to Rekordbox with emoji-based folder placement

    Use --skip-tidal or --skip-rekordbox to run only part of the workflow.
    """
    try:
        # Initialize services
        console.print("[bold blue]🔄 Initializing services...[/bold blue]")
        config = Config()
        db_service = init_db(config=config)

        tidal_synced = False
        rekordbox_synced = False

        # Step 1: Sync Tidal to database
        if not skip_tidal:
            console.print(
                "\n[bold blue]📥 Syncing from Tidal to database...[/bold blue]"
            )
            tidal_api = init_tidal_api()
            tidal_snapshot = TidalSnapshotService(
                tidal_service=tidal_api,
                db_service=db_service,
            )

            result = tidal_snapshot.sync_tidal_to_db(playlist_name=playlist)

            if result["changes_detected"] > 0:
                console.print(
                    f"  [green]✓ Synced "
                    f"{result['sync_state']['counts']['tidal_playlists']} "
                    f"playlists with "
                    f"{result['sync_state']['counts']['tidal_tracks']} "
                    f"tracks[/green]"
                )
                console.print(
                    f"  [yellow]→ {result['changes_detected']} "
                    f"changes detected[/yellow]"
                )
            else:
                console.print("  [dim]✓ No changes detected[/dim]")

            tidal_synced = True
        else:
            console.print("[dim]⏭️  Skipping Tidal sync[/dim]")

        # Step 2: Sync database to Rekordbox
        if not skip_rekordbox:
            console.print(
                "\n[bold blue]📤 Syncing from database to Rekordbox...[/bold blue]"
            )
            rekordbox_service = init_rekordbox()
            rekordbox_snapshot = RekordboxSnapshotService(
                rekordbox_service=rekordbox_service,
                db_service=db_service,
                config=config,
                emoji_config_path=emoji_config,
            )

            result = rekordbox_snapshot.sync_database_to_rekordbox(
                playlist_name=playlist, dry_run=dry_run
            )

            console.print(
                f"  [green]✓ Synced {result['playlists_synced']} playlists "
                f"with {result['tracks_synced']} tracks[/green]"
            )

            if dry_run:
                console.print("  [yellow]⚠️  DRY RUN - No changes were made[/yellow]")

            rekordbox_synced = True
        else:
            console.print("[dim]⏭️  Skipping Rekordbox sync[/dim]")

        # Summary
        console.print("\n[bold green]✅ Sync complete![/bold green]")
        if tidal_synced and rekordbox_synced:
            console.print("  Tidal → Database → Rekordbox")
        elif tidal_synced:
            console.print("  Tidal → Database")
        elif rekordbox_synced:
            console.print("  Database → Rekordbox")

    except Exception as e:
        logger.exception("Sync failed")
        console.print(f"[bold red]❌ Sync failed: {e}[/bold red]")
        raise click.Abort()
