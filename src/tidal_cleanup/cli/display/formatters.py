"""Display formatters and UI helpers for CLI."""

import logging
from typing import Any, List

from rich.console import Console
from rich.table import Table

from ...database import DatabaseService

console = Console()
logger = logging.getLogger(__name__)


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
