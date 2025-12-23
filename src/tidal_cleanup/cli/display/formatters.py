"""Display formatters and UI helpers for CLI."""

import logging
from typing import Any, Dict, List

from rich.console import Console
from rich.table import Table

from ...core.sync import SyncStage
from ...database import DatabaseService

console = Console()
logger = logging.getLogger(__name__)


def display_batch_summary(results: List[Dict[str, Any]]) -> None:
    """Display summary of batch sync operation.

    Args:
        results: List of sync result dictionaries
    """
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


def display_sync_result(result: dict[str, Any], compact: bool = False) -> None:
    """Display sync results.

    Args:
        result: Sync result dictionary
        compact: If True, show compact format for batch operations
    """
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


def display_download_results(result: Any) -> None:
    """Display download operation results.

    Args:
        result: DownloadOrchestrator result object
    """
    console.print("\n[bold green]✓ Download complete[/bold green]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")

    table.add_row("Downloads Attempted", str(result.downloads_attempted))
    table.add_row("Downloads Successful", str(result.downloads_successful))
    table.add_row("Downloads Failed", str(result.downloads_failed))

    console.print(table)

    if result.errors:
        console.print(f"\n[yellow]⚠️  {len(result.errors)} error(s) occurred:[/yellow]")
        for error in result.errors[:10]:
            console.print(f"  • {error}")


def display_db_sync_result(summary: dict[str, Any], dry_run: bool) -> None:
    """Display database sync results.

    Args:
        summary: Sync summary dictionary with statistics
        dry_run: Whether this was a dry run
    """
    console.print("\n[bold green]✓ Sync operation completed[/bold green]\n")

    stage_info = summary.get("stage")
    if stage_info:
        table = Table(
            show_header=True,
            header_style="bold magenta",
            title="Stage Progress",
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        requested = stage_info.get("requested") or SyncStage.EXECUTION.value
        completed = stage_info.get("completed") or SyncStage.EXECUTION.value
        status = (
            "Reached requested stage" if requested == completed else "Stopped early"
        )

        table.add_row("Requested Stop", requested.title())
        table.add_row("Completed Stage", completed.title())
        table.add_row("Status", status)

        console.print(table)
        console.print()

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
        table.add_row(
            "Tracks in Multiple Playlists",
            str(dedup.get("tracks_in_multiple_playlists", 0)),
        )

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

        console.print(table)


def filter_decisions_by_playlist(
    db_service: DatabaseService,
    download_decisions: List[Any],
    playlist_name: str,
) -> List[Any]:
    """Filter download decisions by playlist name.

    Args:
        db_service: Database service instance
        download_decisions: List of download decisions
        playlist_name: Playlist name to filter by (fuzzy match)

    Returns:
        Filtered list of download decisions
    """
    with db_service.get_session() as session:
        from ...database.models import Playlist

        target_playlist = (
            session.query(Playlist)
            .filter(Playlist.name.ilike(f"%{playlist_name}%"))
            .first()
        )

        if not target_playlist:
            console.print(
                f"[yellow]⚠️  No playlist found matching '{playlist_name}'[/yellow]"
            )
            return []

        filtered = [
            d for d in download_decisions if d.playlist_id == target_playlist.id
        ]
        console.print(f"[cyan]Filtered to playlist: {target_playlist.name}[/cyan]")
        return filtered
