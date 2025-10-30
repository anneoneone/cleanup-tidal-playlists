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


@click.command()
@click.option(
    "--emoji-config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to emoji-to-MyTag mapping config (uses default if not specified)",
)
@click.pass_context
def sync_all_two_step(
    ctx: click.Context,
    emoji_config: Optional[Path],
) -> None:
    """Execute the new two-step sync algorithm for all playlists.

    Step 1: Creates/updates intelligent playlist structure based on
            rekordbox_mytag_mapping.json
      - Creates "Genres" and "Events" top-level directories
      - Creates genre hierarchy with intelligent playlists
      - Creates event subdirectories

    Step 2: Syncs track tags from MP3 playlist directories
      - Parses directory names for tag metadata
      - Adds/updates tracks with proper MyTags
      - Removes tags from tracks not in playlists (Tidal only)
      - Applies defaults: Status=Archived, Source=Tidal

    This replaces the old playlist-by-playlist sync approach with a more
    systematic structure-first, then tags approach.
    """
    # Setup logging
    setup_logging()

    config = Config()

    try:
        # Initialize service
        rekordbox_service = RekordboxService(config)

        console.print("\n[bold cyan]🎵 Two-Step Rekordbox Sync Algorithm[/bold cyan]")
        console.print("=" * 60)
        console.print("Step 1: Intelligent playlist structure")
        console.print("Step 2: Track tag synchronization")
        console.print("=" * 60 + "\n")

        # Execute two-step sync
        results = rekordbox_service.sync_all_with_two_step_algorithm(
            emoji_config_path=emoji_config
        )

        # Display results
        _display_two_step_results(results)

    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        raise click.Abort()
    except Exception as e:
        logger.error(f"❌ Error during two-step sync: {e}")
        import traceback

        traceback.print_exc()
        raise click.Abort()


def _display_two_step_results(results: dict[str, Any]) -> None:
    """Display two-step sync results."""
    console.print("\n[bold green]✅ Two-step sync completed![/bold green]\n")

    # Step 1 results
    console.print("[bold cyan]Step 1: Intelligent Playlist Structure[/bold cyan]")
    step1_table = Table(show_header=True, header_style="bold magenta")
    step1_table.add_column("Metric", style="cyan", width=30)
    step1_table.add_column("Value", style="green", justify="right")

    step1 = results.get("step1", {})
    step1_table.add_row("Genres Created", str(step1.get("genres_created", 0)))
    step1_table.add_row("Genres Updated", str(step1.get("genres_updated", 0)))
    step1_table.add_row(
        "Event Folders Created", str(step1.get("events_folders_created", 0))
    )
    step1_table.add_row("Total Playlists", str(step1.get("total_playlists", 0)))

    console.print(step1_table)
    console.print()

    # Step 2 results
    console.print("[bold cyan]Step 2: Track Tag Synchronization[/bold cyan]")
    step2_table = Table(show_header=True, header_style="bold magenta")
    step2_table.add_column("Metric", style="cyan", width=30)
    step2_table.add_column("Value", style="green", justify="right")

    step2 = results.get("step2", {})
    step2_table.add_row("Playlists Processed", str(step2.get("playlists_processed", 0)))
    step2_table.add_row("Tracks Added", str(step2.get("tracks_added", 0)))
    step2_table.add_row("Tracks Updated", str(step2.get("tracks_updated", 0)))
    step2_table.add_row("Tracks Removed", str(step2.get("tracks_removed", 0)))
    step2_table.add_row("Skipped Playlists", str(step2.get("skipped_playlists", 0)))

    console.print(step2_table)
    console.print()


if __name__ == "__main__":
    sync_playlist()
