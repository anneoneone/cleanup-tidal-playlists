"""Command-line interface for the Tidal cleanup application."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.table import Table

from tidal_cleanup.models.models import ConversionJob

from ..config import get_config
from ..services import (
    DeletionMode,
    FileService,
    PlaylistSynchronizer,
    RekordboxGenerationError,
    RekordboxService,
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

    def _convert_files(self) -> None:
        """Convert M4A files to MP3."""
        console.print("[bold blue]Converting audio files...[/bold blue]")

        playlist_jobs = self.file_service.convert_directory_with_playlist_reporting(
            self.config.m4a_directory,
            self.config.mp3_directory,
            target_format=".mp3",
            quality=self.config.ffmpeg_quality,
        )

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
        total_failed = 0

        console.print("\nConversion complete:")

        # Collect all stats first
        playlist_stats = {}
        for playlist_name, jobs in playlist_jobs.items():
            converted = len(
                [j for j in jobs if j.status == "completed" and not j.was_skipped]
            )
            skipped = len([j for j in jobs if j.was_skipped])
            failed = len([j for j in jobs if j.status == "failed"])

            playlist_stats[playlist_name] = {
                "converted": converted,
                "skipped": skipped,
                "failed": failed,
            }

            total_converted += converted
            total_skipped += skipped
            total_failed += failed

        # Create a table for proper alignment
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Playlist", style="bold white", no_wrap=True)
        table.add_column("Converted", style="green", justify="right")
        table.add_column("", style="none")  # "converted" text
        table.add_column("Skipped", style="yellow", justify="right")
        table.add_column("", style="none")  # "skipped" text
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
                str(stats["failed"]),
                "failed",
            )

        # Add overall summary row
        table.add_row("", "", "", "", "", "", "")  # Empty row for spacing
        table.add_row(
            "[bold cyan]Overall Summary[/bold cyan]",
            f"[green]{total_converted}[/green]",
            "converted",
            f"[yellow]{total_skipped}[/yellow]",
            "skipped",
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
@click.pass_obj
def convert(app: TidalCleanupApp) -> None:
    """Convert audio files from M4A to MP3."""
    app._convert_files()


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


if __name__ == "__main__":
    cli()
