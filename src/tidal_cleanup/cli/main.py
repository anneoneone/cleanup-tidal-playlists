"""Command-line interface for the Tidal cleanup application."""

import logging
from pathlib import Path
from typing import Any, List, Optional

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

# Try to import and register the sync-playlist command
sync_playlist: Optional[click.Command]
try:
    from .rekordbox import sync_playlist

    SYNC_PLAYLIST_AVAILABLE = True
    logger.debug("sync-playlist command imported successfully")
except ImportError as e:
    logger.debug(f"sync-playlist command not available: {e}")
    SYNC_PLAYLIST_AVAILABLE = False
    sync_playlist = None


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
    "--playlist", "-p", help="Sync only a specific playlist (uses fuzzy matching)"
)
@click.option(
    "--auto-delete",
    is_flag=True,
    help="Automatically delete local tracks not in Tidal playlist without asking",
)
@click.option(
    "--auto-skip",
    is_flag=True,
    help="Skip deletion of local tracks not in Tidal playlist without asking",
)
@click.pass_obj
def sync(
    app: TidalCleanupApp,
    playlist: Optional[str],
    auto_delete: bool,
    auto_skip: bool,
) -> None:
    """Synchronize Tidal playlists with local files."""
    # Validate conflicting options
    if auto_delete and auto_skip:
        raise click.ClickException(
            "Cannot use both --auto-delete and --auto-skip at the same time"
        )

    # Determine deletion mode
    if auto_delete:
        deletion_mode = DeletionMode.AUTO_DELETE
    elif auto_skip:
        deletion_mode = DeletionMode.AUTO_SKIP
    else:
        deletion_mode = DeletionMode.ASK

    success = app.sync_playlists(playlist_filter=playlist, deletion_mode=deletion_mode)
    if not success:
        raise click.ClickException("Synchronization failed")


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


# Register the sync-playlist command if available
if sync_playlist is not None:
    cli.add_command(sync_playlist, name="sync-playlist")


if __name__ == "__main__":
    cli()
