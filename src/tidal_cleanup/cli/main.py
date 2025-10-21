"""Command-line interface for the Tidal cleanup application."""

import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from ..config import get_config
from ..services import (
    FileOperationError,
    FileService,
    RekordboxGenerationError,
    RekordboxService,
    TidalConnectionError,
    TidalService,
    TrackComparisonService,
)
from ..utils.logging_config import configure_third_party_loggers, setup_logging

console = Console()
logger = logging.getLogger(__name__)


class TidalCleanupApp:
    """Main application class."""

    def __init__(self, config_override: Optional[dict] = None):
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

    def sync_playlists(self) -> bool:
        """Synchronize Tidal playlists with local files.

        Returns:
            True if successful, False otherwise
        """
        try:
            console.print("[bold blue]Starting playlist synchronization...[/bold blue]")

            # Connect to Tidal
            with console.status("[bold green]Connecting to Tidal..."):
                self.tidal_service.connect()

            console.print("[green]✓[/green] Connected to Tidal")

            # Get playlists
            with console.status("[bold green]Fetching playlists..."):
                playlists = self.tidal_service.get_playlists()

            console.print(f"[green]✓[/green] Found {len(playlists)} playlists")

            # Process each playlist
            processed = 0
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:

                task = progress.add_task(
                    "Processing playlists...", total=len(playlists)
                )

                for playlist in playlists:
                    try:
                        self._process_playlist(playlist, progress, task)
                        processed += 1
                    except Exception as e:
                        logger.error(f"Failed to process playlist {playlist.name}: {e}")
                        console.print(
                            f"[red]✗[/red] Failed to process playlist: {playlist.name}"
                        )

                    progress.advance(task)

            console.print(
                f"[green]✓[/green] Processed {processed}/{len(playlists)} playlists"
            )

            # Convert files
            self._convert_files()

            return True

        except TidalConnectionError as e:
            console.print(f"[red]✗[/red] Tidal connection failed: {e}")
            return False
        except Exception as e:
            logger.exception("Playlist synchronization failed")
            console.print(f"[red]✗[/red] Synchronization failed: {e}")
            return False

    def _process_playlist(self, playlist, progress, task):
        """Process a single playlist."""
        progress.update(task, description=f"Processing {playlist.name}...")

        # Check if local folder exists
        m4a_folder = self.config.m4a_directory / "Playlists" / playlist.name
        if not m4a_folder.exists():
            logger.warning(f"Local folder not found for playlist: {playlist.name}")
            return

        # Get Tidal tracks
        tidal_tracks = self.tidal_service.get_playlist_tracks(playlist.tidal_id)

        # Get local tracks
        local_track_names = self.file_service.get_track_names(m4a_folder)
        tidal_track_names = {track.normalized_name for track in tidal_tracks}

        # Compare tracks
        comparison = self.comparison_service.compare_track_sets(
            local_track_names, tidal_track_names, playlist.name
        )

        # Get tracks to delete
        tracks_to_delete = self.comparison_service.get_tracks_to_delete(comparison)

        # Delete unmatched tracks
        self._delete_tracks(m4a_folder, tracks_to_delete)

        # Also process MP3 folder
        mp3_folder = self.config.mp3_directory / "Playlists" / playlist.name
        if mp3_folder.exists():
            self._sync_mp3_folder(m4a_folder, mp3_folder)

    def _delete_tracks(self, folder: Path, tracks_to_delete: set):
        """Delete tracks that are not in Tidal playlist."""
        for track_name in tracks_to_delete:
            # Find matching files with fuzzy search
            match_result = self.comparison_service.find_best_match(
                track_name,
                [
                    f.stem
                    for f in folder.rglob("*")
                    if f.suffix.lower() in self.config.audio_extensions
                ],
            )

            if match_result:
                best_match, score = match_result
                # Find the actual file
                for ext in self.config.audio_extensions:
                    file_path = folder / f"{best_match}{ext}"
                    if file_path.exists():
                        if self._confirm_deletion(file_path):
                            self.file_service.delete_file(file_path, interactive=False)
                        break

    def _confirm_deletion(self, file_path: Path) -> bool:
        """Confirm file deletion with user."""
        if not self.config.interactive_mode:
            return True

        return click.confirm(f"Delete {file_path.name}?", default=False)

    def _sync_mp3_folder(self, m4a_folder: Path, mp3_folder: Path):
        """Sync MP3 folder with M4A folder."""
        # Get track names from both folders
        m4a_tracks = self.file_service.get_track_names(m4a_folder)
        mp3_tracks = self.file_service.get_track_names(mp3_folder)

        # Find MP3 files that don't have M4A equivalent
        missing_in_m4a = mp3_tracks - m4a_tracks

        # Delete orphaned MP3 files
        for track_name in missing_in_m4a:
            mp3_file = mp3_folder / f"{track_name}.mp3"
            if mp3_file.exists():
                if self._confirm_deletion(mp3_file):
                    self.file_service.delete_file(mp3_file, interactive=False)

    def _convert_files(self):
        """Convert M4A files to MP3."""
        console.print("[bold blue]Converting audio files...[/bold blue]")

        jobs = self.file_service.convert_directory(
            self.config.m4a_directory,
            self.config.mp3_directory,
            target_format=".mp3",
            quality=self.config.ffmpeg_quality,
        )

        successful = len([j for j in jobs if j.status == "completed"])
        failed = len([j for j in jobs if j.status == "failed"])

        console.print(
            f"[green]✓[/green] Conversion complete: {successful} successful, {failed} failed"
        )

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
                f"[green]✓[/green] Rekordbox XML generated: {self.config.rekordbox_output_file}"
            )
            return True

        except RekordboxGenerationError as e:
            console.print(f"[red]✗[/red] Rekordbox generation failed: {e}")
            return False
        except Exception as e:
            logger.exception("Rekordbox XML generation failed")
            console.print(f"[red]✗[/red] Rekordbox generation failed: {e}")
            return False

    def show_status(self):
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
def cli(ctx, log_level, log_file, no_interactive):
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
@click.pass_obj
def sync(app):
    """Synchronize Tidal playlists with local files."""
    success = app.sync_playlists()
    if not success:
        raise click.ClickException("Synchronization failed")


@cli.command()
@click.pass_obj
def convert(app):
    """Convert audio files from M4A to MP3."""
    app._convert_files()


@cli.command()
@click.pass_obj
def rekordbox(app):
    """Generate Rekordbox XML file."""
    success = app.generate_rekordbox_xml()
    if not success:
        raise click.ClickException("Rekordbox XML generation failed")


@cli.command()
@click.pass_obj
def status(app):
    """Show configuration and status."""
    app.show_status()


@cli.command()
@click.pass_obj
def full(app):
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
