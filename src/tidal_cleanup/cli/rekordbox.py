"""Command-line interface for Rekordbox playlist management."""

import logging
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..services.rekordbox_service import RekordboxService
from ..utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
console = Console()


@click.command()
@click.argument("playlist_name", type=str)
@click.option(
    "--emoji-config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to emoji-to-MyTag mapping config (uses default if not specified)",
)
@click.pass_context
def sync_playlist(
    ctx: click.Context,
    playlist_name: str,
    emoji_config: Optional[Path],
) -> None:
    """Sync an MP3 playlist to Rekordbox with emoji-based MyTag management.

    This command synchronizes a playlist from your MP3 folder to Rekordbox,
    automatically managing MyTags based on emojis in the playlist name.

    Playlist Name Pattern: "NAME [GENRE/PARTY-EMOJI] [ENERGY-EMOJI] [STATUS-EMOJI]"

    Examples:
      - "House Italo R 🇮🇹❓" → Genre: House Italo, Status: Recherche
      - "Jazzz D 🎷💾" → Genre: Jazz, Status: Archived
      - "Party Mix 🎉⚡" → Party: Party, Energy: High Energy

    Features:
      - Adds/removes tracks based on MP3 folder contents
      - Applies MyTags from emoji patterns in playlist name
      - Handles tracks in multiple playlists (accumulates tags)
      - Removes playlist-specific tags when tracks are removed
      - Deletes empty playlists automatically

    PLAYLIST_NAME: Exact name of the playlist folder in your MP3 directory
    """
    # Setup logging
    setup_logging()

    config = Config()

    try:
        # Initialize service
        rekordbox_service = RekordboxService(config)

        console.print("\n[bold cyan]🎵 Rekordbox Playlist Synchronization[/bold cyan]")
        console.print("=" * 60)
        console.print(f"Playlist: [bold]{playlist_name}[/bold]\n")

        # Use the new MyTag-based sync
        result = rekordbox_service.sync_playlist_with_mytags(
            playlist_name, emoji_config_path=emoji_config
        )

        # Display results
        _display_sync_results(result)

    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        raise click.Abort()
    except Exception as e:
        logger.error(f"❌ Error syncing playlist: {e}")
        import traceback

        traceback.print_exc()
        raise click.Abort()


def _display_sync_results(result: dict[str, Any]) -> None:
    """Display sync results in a nice table format."""
    console.print("\n[bold green]✅ Sync completed successfully![/bold green]\n")

    # Create results table
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


if __name__ == "__main__":
    sync_playlist()
