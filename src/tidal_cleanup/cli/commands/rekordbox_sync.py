"""CLI command for syncing database playlists into Rekordbox."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import click
from rich.console import Console
from rich.table import Table

from ...config import Config
from ...core.rekordbox.snapshot_service import RekordboxSnapshotService
from .init import init

logger = logging.getLogger(__name__)
console = Console()


@click.command("sync-rekordbox")
@click.option(
    "--playlist",
    "-p",
    type=str,
    help="Sync only a single playlist by name",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the planned Rekordbox changes without applying them",
)
@click.option(
    "--no-prune",
    is_flag=True,
    help="Keep tracks that exist only in Rekordbox playlists",
)
@click.option(
    "--emoji-config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to emoji-to-MyTag mapping config (defaults to project config)",
)
def sync_rekordbox_command(
    playlist: Optional[str], dry_run: bool, no_prune: bool, emoji_config: Optional[Path]
) -> None:
    """Sync database playlists to the local Rekordbox collection."""
    config = Config()
    db_service, _tidal_service, _download_service, rekordbox_service = init(config)

    if rekordbox_service is None or rekordbox_service.db is None:
        raise click.ClickException("Rekordbox service is not available")

    sync_service = RekordboxSnapshotService(
        rekordbox_service,
        db_service,
        config,
        emoji_config_path=emoji_config,
    )
    summary = sync_service.sync_database_to_rekordbox(
        playlist_name=playlist,
        dry_run=dry_run,
        prune_extra=not no_prune,
    )

    _display_summary(summary, dry_run)

    if summary.get("errors"):
        for error in summary["errors"]:
            logger.error("Rekordbox sync error: %s", error)
        raise click.ClickException("One or more playlists failed to sync")


def _display_summary(summary: Dict[str, Any], dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLY"
    console.print(f"\n[bold cyan]📀 Rekordbox Sync ({mode})[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Playlists processed", str(summary["playlists_processed"]))
    table.add_row("Playlists created", str(summary["playlists_created"]))
    table.add_row("Playlists changed", str(summary["playlists_changed"]))
    table.add_row("Tracks added", str(summary["tracks_added"]))
    table.add_row("Tracks removed", str(summary["tracks_removed"]))
    table.add_row("Tracks skipped", str(summary["tracks_skipped"]))

    console.print(table)

    if summary.get("errors"):
        console.print("\n[bold red]Errors:[/bold red]")
        for error in summary["errors"]:
            console.print(f"  • {error}")
    else:
        console.print("[green]✓ Rekordbox playlists are synchronized[/green]")
