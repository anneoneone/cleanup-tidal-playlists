"""Legacy CLI commands for Tidal cleanup application.

This module contains the original command-line interface commands that work with the
service layer (not the database layer).
"""

import logging
from pathlib import Path
from typing import Any, List, Optional

import click
from rich.console import Console
from rich.table import Table

from tidal_cleanup.models.models import ConversionJob

from ...config import get_config
from ...services import (
    DeletionMode,
    FileService,
    PlaylistSynchronizer,
    RekordboxService,
    TidalApiService,
    TidalDownloadError,
    TidalDownloadService,
    TrackComparisonService,
)
from ..display import display_batch_summary, display_sync_result

console = Console()
logger = logging.getLogger(__name__)


class TidalCleanupApp:
    """Main application class for legacy commands."""

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
        self.tidal_service = TidalApiService(self.config.tidal_token_file)
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

        # Initialize download service
        self.download_service = TidalDownloadService(self.config)

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

    def _download_tracks(self, playlist_name: Optional[str] = None) -> None:
        """Download tracks from Tidal to M4A directory.

        Args:
            playlist_name: Optional playlist name to download. If provided,
                          only that playlist will be downloaded.
        """
        try:
            # Connect to Tidal
            with console.status("[bold green]Connecting to Tidal..."):
                self.download_service.connect()
            console.print("[green]✓[/green] Connected to Tidal")

            if playlist_name:
                console.print(
                    f"[bold blue]Downloading playlist: {playlist_name}...[/bold blue]"
                )
                playlist_dir = self.download_service.download_playlist(playlist_name)
                console.print(
                    f"[green]✓[/green] Downloaded playlist to: {playlist_dir}"
                )
            else:
                console.print("[bold blue]Downloading all playlists...[/bold blue]")
                playlist_dirs = self.download_service.download_all_playlists()
                console.print(
                    f"[green]✓[/green] Downloaded {len(playlist_dirs)} playlists"
                )

        except TidalDownloadError as e:
            console.print(f"[red]✗[/red] Download failed: {e}")
            raise click.ClickException(str(e))
        except Exception as e:
            logger.exception("Download failed")
            console.print(f"[red]✗[/red] Download failed: {e}")
            raise click.ClickException(str(e))

    def _convert_files(self, playlist_name: Optional[str] = None) -> None:
        """Convert M4A files to MP3.

        DEPRECATED: This method is no longer supported.
        Use 'tidal-cleanup download' with --target-format instead.

        Args:
            playlist_name: Optional playlist name to convert. If provided,
                          only the closest matching playlist will be converted.
        """
        console.print(
            "[yellow]⚠ This command is deprecated. "
            "Use 'tidal-cleanup download --target-format mp3' instead.[/yellow]"
        )

    def generate_rekordbox_xml(self) -> bool:
        """Generate Rekordbox XML file.

        DEPRECATED: This method is no longer supported.
        Use 'tidal-cleanup rekordbox sync' instead.

        Returns:
            True if successful, False otherwise
        """
        console.print(
            "[yellow]⚠ This command is deprecated. "
            "Use 'tidal-cleanup rekordbox sync' instead.[/yellow]"
        )
        return False

    def show_result_table(self, playlist_jobs: dict[str, List[ConversionJob]]) -> None:
        """Show result of playlist conversion."""
        total_converted = 0
        total_skipped = 0
        total_deleted = 0
        total_failed = 0

        console.print("\nConversion complete:")

        # Collect all stats first
        playlist_stats = {}
        for playlist_name, jobs in playlist_jobs.items():
            converted = len(
                [j for j in jobs if j.status == "completed" and not j.was_skipped]
            )
            skipped = len([j for j in jobs if j.was_skipped])
            deleted = len([j for j in jobs if j.status == "deleted"])
            failed = len([j for j in jobs if j.status == "failed"])

            playlist_stats[playlist_name] = {
                "converted": converted,
                "skipped": skipped,
                "deleted": deleted,
                "failed": failed,
            }

            total_converted += converted
            total_skipped += skipped
            total_deleted += deleted
            total_failed += failed

        # Create a table for proper alignment
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Playlist", style="bold white", no_wrap=True)
        table.add_column("Converted", style="green", justify="right")
        table.add_column("", style="none")  # "converted" text
        table.add_column("Skipped", style="yellow", justify="right")
        table.add_column("", style="none")  # "skipped" text
        table.add_column("Deleted", style="red", justify="right")
        table.add_column("", style="none")  # "deleted" text
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
                str(stats["deleted"]),
                "deleted",
                str(stats["failed"]),
                "failed",
            )

        # Add overall summary row
        table.add_row("", "", "", "", "", "", "", "", "")  # Empty row for spacing
        table.add_row(
            "[bold cyan]Overall Summary[/bold cyan]",
            f"[green]{total_converted}[/green]",
            "converted",
            f"[yellow]{total_skipped}[/yellow]",
            "skipped",
            f"[red]{total_deleted}[/red]",
            "deleted",
            f"[red]{total_failed}[/red]",
            "failed",
        )

        console.print(table)

    def show_status(self) -> None:
        """Show application status and configuration."""
        table = Table(title="Tidal Cleanup Configuration")

        table.add_column("Setting", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        table.add_row("MP3 Directory", str(self.config.mp3_directory))
        table.add_row("Token File", str(self.config.tidal_token_file))
        table.add_row("Fuzzy Threshold", str(self.config.fuzzy_match_threshold))
        table.add_row("Database Path", str(self.config.database_path))

        console.print(table)


def sync_all_playlists_impl(
    rekordbox_service: RekordboxService,
    playlists_dir: Path,
    emoji_config: Optional[Path],
) -> None:
    """Sync all playlists in the playlists directory.

    Args:
        rekordbox_service: Rekordbox service instance
        playlists_dir: Directory containing playlist folders
        emoji_config: Optional path to emoji config file
    """
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
            display_sync_result(result, compact=True)
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            logger.error("Failed to sync playlist %s: %s", playlist_name, e)

    # Display summary
    display_batch_summary(results)


def sync_command(
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
            display_sync_result(result)
        else:
            # Sync all playlists
            playlists_dir = app.config.mp3_directory / "Playlists"
            sync_all_playlists_impl(rekordbox_service, playlists_dir, emoji_config)

    except FileNotFoundError as e:
        logger.error("❌ %s", e)
        raise click.Abort()
    except Exception as e:
        logger.error("❌ Error syncing: %s", e)
        import traceback

        traceback.print_exc()
        raise click.Abort()


@click.command("legacy_sync")
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
def legacy_sync(
    app: TidalCleanupApp,
    playlist: Optional[str],
    emoji_config: Optional[Path],
) -> None:
    """Synchronize MP3 playlists to Rekordbox."""
    sync_command(app, playlist, emoji_config)


@click.command("legacy_convert")
@click.option(
    "-p",
    "--playlist",
    type=str,
    default=None,
    help="Convert only the playlist with closest match to the given name",
)
@click.pass_obj
def legacy_convert(app: TidalCleanupApp, playlist: Optional[str]) -> None:
    """Convert audio files from M4A to MP3."""
    app._convert_files(playlist_name=playlist)


@click.command("status")
@click.pass_obj
def status(app: TidalCleanupApp) -> None:
    """Show configuration and status."""
    app.show_status()


@click.command("legacy_full")
@click.pass_obj
def legacy_full(app: TidalCleanupApp) -> None:
    """Run full workflow: sync, convert, and generate Rekordbox XML."""
    console.print("[bold green]Running full workflow...[/bold green]")

    # Sync playlists
    if not app.sync_playlists():
        raise click.ClickException("Synchronization failed")

    # Generate Rekordbox XML
    if not app.generate_rekordbox_xml():
        raise click.ClickException("Rekordbox XML generation failed")

    console.print("[bold green]✓ Full workflow completed successfully![/bold green]")
