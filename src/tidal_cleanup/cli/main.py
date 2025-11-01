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
    TrackTagSyncService,
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


@cli.command(name="sync")
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
def sync_command(
    app: TidalCleanupApp,
    playlist: Optional[str],
    emoji_config: Optional[Path],
) -> None:
    """Sync MP3 playlists to Rekordbox with MyTag management."""
    sync(app, playlist, emoji_config)


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
      - "Party Name 🎉" → Event: Party
      - "Set Name 🎶" → Event: Set
      - "Radio Show 🎙️" → Event: Radio Moafunk

    Features:
      - Adds/removes tracks based on MP3 folder contents
      - Applies MyTags from emoji patterns in playlist names
      - Creates intelligent playlists for event playlists under Events/
      - Handles tracks in multiple playlists (accumulates tags)
      - Removes playlist-specific tags when tracks are removed
      - Deletes empty playlists automatically
    """
    try:
        # Get emoji config path
        if emoji_config is None:
            config_parent = Path(__file__).parent.parent.parent.parent
            emoji_config = config_parent / "config" / "rekordbox_mytag_mapping.json"
            if not emoji_config.exists():
                emoji_config = Path.cwd() / "config" / "rekordbox_mytag_mapping.json"

        if not emoji_config.exists():
            console.print(f"[red]❌ Emoji config not found: {emoji_config}[/red]")
            raise click.Abort()

        # Initialize parser to detect playlist types
        from ..services.playlist_name_parser import PlaylistNameParser

        parser = PlaylistNameParser(emoji_config)

        if playlist:
            # Sync single playlist - detect type and route appropriately
            console.print(f"\n[bold cyan]🎵 Syncing playlist: {playlist}[/bold cyan]")
            console.print("=" * 60)

            metadata = parser.parse_playlist_name(playlist)
            is_event = bool(
                metadata.party_tags or metadata.set_tags or metadata.radio_moafunk_tags
            )

            if is_event:
                # Use TrackTagSyncService for event playlists
                _sync_event_playlist_single(app, playlist, emoji_config)
            else:
                # Use RekordboxService for genre playlists
                rekordbox_service = RekordboxService(app.config)
                result = rekordbox_service.sync_playlist_with_mytags(
                    playlist, emoji_config_path=emoji_config
                )
                _display_sync_result(result)
        else:
            # Sync all playlists - separate into genre and event playlists
            _sync_all_playlists_intelligent(app, emoji_config, parser)

    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        raise click.Abort()
    except Exception as e:
        logger.error(f"❌ Error syncing: {e}")
        import traceback

        traceback.print_exc()
        raise click.Abort()


def _sync_event_playlist_single(
    app: TidalCleanupApp, playlist: str, emoji_config: Path
) -> None:
    """Sync a single event playlist using TrackTagSyncService."""
    from pyrekordbox.db6 import Rekordbox6Database

    try:
        db = Rekordbox6Database()
        logger.info("Connected to Rekordbox database")
    except Exception as e:
        console.print(f"[red]❌ Failed to connect to Rekordbox database: {e}[/red]")
        raise click.Abort()

    mp3_playlists_root = app.config.mp3_directory / "Playlists"

    if not mp3_playlists_root.exists():
        console.print(
            f"[red]❌ MP3 playlists directory not found: " f"{mp3_playlists_root}[/red]"
        )
        raise click.Abort()

    sync_service = TrackTagSyncService(
        db=db,
        mp3_playlists_root=mp3_playlists_root,
        mytag_mapping_path=emoji_config,
    )

    result = sync_service.sync_playlist(playlist)
    db.commit()
    db.close()
    _display_event_sync_result(result)


def _sync_all_playlists_intelligent(
    app: TidalCleanupApp, emoji_config: Path, parser: Any
) -> None:
    """Sync all playlists with proper structure creation and track tagging.

    Workflow:
    1. Parse all playlist names and create playlist structure
    2. Create all intelligent playlists upfront
    3. Process tracks and tag them with MyTags
    """
    console.print("\n[bold cyan]🎵 Syncing all playlists to Rekordbox[/bold cyan]")
    console.print("=" * 60)

    # Collect and categorize playlists
    genre_playlists, event_playlists = _collect_playlists(app, parser)

    if not genre_playlists and not event_playlists:
        console.print("[yellow]⚠️ No playlist folders found[/yellow]")
        return

    console.print(
        f"\n[bold]Found {len(genre_playlists) + len(event_playlists)} playlists: "
        f"{len(genre_playlists)} genre, {len(event_playlists)} event[/bold]\n"
    )

    # Initialize database
    db = _initialize_database()

    try:
        # Initialize structure service
        structure_service = _create_playlist_structure(db, emoji_config)

        # Initialize sync service with structure service
        sync_service = _initialize_sync_service(
            app, db, emoji_config, structure_service
        )

        # Phase 1: Create all playlist structures upfront
        console.print("\n[bold cyan]Phase 1: Creating playlist structures[/bold cyan]")
        playlist_mapping = _create_all_playlists(
            genre_playlists, event_playlists, sync_service, parser, db
        )
        console.print(
            f"[green]✓ Created {len(playlist_mapping)} playlist structures[/green]\n"
        )

        # Phase 2: Tag all tracks
        console.print("\n[bold cyan]Phase 2: Tagging tracks[/bold cyan]")
        _tag_all_tracks(playlist_mapping, sync_service, db)
        console.print("[green]✓ All tracks tagged[/green]\n")

        # Phase 3: Sort playlists alphabetically
        console.print(
            "\n[bold cyan]Phase 3: Sorting playlists alphabetically[/bold cyan]"
        )
        sort_counts = structure_service.sort_playlists_alphabetically()
        console.print(
            f"[green]✓ Sorted {sort_counts['folders']} folders and "
            f"{sort_counts['playlists']} playlists alphabetically[/green]\n"
        )

        console.print("\n[bold green]✅ All playlists synchronized![/bold green]")
    finally:
        db.close()


def _collect_playlists(
    app: TidalCleanupApp, parser: Any
) -> tuple[list[str], list[str]]:
    """Collect and categorize playlists into genre and event lists."""
    playlists_dir = app.config.mp3_directory / "Playlists"

    if not playlists_dir.exists():
        console.print(f"[red]❌ Playlists directory not found: {playlists_dir}[/red]")
        raise click.Abort()

    playlist_folders = [d for d in playlists_dir.iterdir() if d.is_dir()]
    genre_playlists = []
    event_playlists = []

    for folder in playlist_folders:
        metadata = parser.parse_playlist_name(folder.name)
        is_event = bool(
            metadata.party_tags or metadata.set_tags or metadata.radio_moafunk_tags
        )
        if is_event:
            event_playlists.append(folder.name)
        else:
            genre_playlists.append(folder.name)

    return genre_playlists, event_playlists


def _initialize_database() -> Any:
    """Initialize and return Rekordbox database connection."""
    from pyrekordbox.db6 import Rekordbox6Database

    try:
        db = Rekordbox6Database()
        logger.info("Connected to Rekordbox database")
        return db
    except Exception as e:
        console.print(f"[red]❌ Failed to connect to Rekordbox database: {e}[/red]")
        raise click.Abort()


def _create_playlist_structure(db: Any, emoji_config: Path) -> Any:
    """Initialize intelligent playlist structure service (on-demand creation)."""
    from ..services.intelligent_playlist_structure_service import (
        IntelligentPlaylistStructureService,
    )

    console.print(
        "[cyan]📁 Initializing playlist structure service "
        "(playlists will be created on-demand)...[/cyan]"
    )
    try:
        structure_service = IntelligentPlaylistStructureService(
            db=db,
            mytag_mapping_path=emoji_config,
        )

        console.print(
            "[green]✓ Service initialized (no playlists created yet)[/green]\n"
        )
        return structure_service
    except Exception as e:
        console.print(f"[red]❌ Failed to initialize structure service: {e}[/red]")
        logger.error(f"Structure service initialization failed: {e}", exc_info=True)
        raise click.Abort()


def _initialize_sync_service(
    app: TidalCleanupApp,
    db: Any,
    emoji_config: Path,
    structure_service: Any,
) -> TrackTagSyncService:
    """Initialize TrackTagSyncService with structure service for on-demand creation."""
    mp3_playlists_root = app.config.mp3_directory / "Playlists"
    sync_service = TrackTagSyncService(
        db=db,
        mp3_playlists_root=mp3_playlists_root,
        mytag_mapping_path=emoji_config,
        structure_service=structure_service,
    )

    return sync_service


def _create_all_playlists(
    genre_playlists: list[str],
    event_playlists: list[str],
    sync_service: TrackTagSyncService,
    parser: Any,
    db: Any,
) -> Dict[str, Dict[str, Any]]:
    """Phase 1: Parse all playlists and create their structures.

    Returns:
        Dictionary mapping playlist_name to metadata:
        {
            "playlist_name": {
                "metadata": PlaylistMetadata,
                "type": "genre" or "event",
                "event_type": Optional[str],  # For events: Party, Set, Radio Moafunk
                "event_tag_id": Optional[str],  # For events: MyTag ID
                "folder_path": str  # Full path to MP3 directory
            }
        }
    """
    playlist_mapping: Dict[str, Dict[str, Any]] = {}

    # Ensure Events folder structure exists
    if event_playlists:
        console.print("[cyan]Creating Events folder structure...[/cyan]")
        sync_service._ensure_events_folder_structure()
        db.commit()
        console.print("[green]✓ Events folder structure created[/green]")

    # Process genre playlists
    for playlist_name in genre_playlists:
        console.print(f"[dim]Parsing: {playlist_name}[/dim]")
        metadata = parser.parse_playlist_name(playlist_name)

        # Create intelligent playlists for genre combinations
        if sync_service.structure_service and metadata.genre_tags:
            sync_service._ensure_intelligent_playlists_exist(metadata)

        playlist_mapping[playlist_name] = {
            "metadata": metadata,
            "type": "genre",
            "folder_path": str(sync_service.mp3_playlists_root / playlist_name),
        }

    # Commit genre playlist structures
    if genre_playlists:
        db.commit()
        console.print(
            f"[green]✓ Created {len(genre_playlists)} "
            "genre playlist structures[/green]"
        )

    # Process event playlists
    for playlist_name in event_playlists:
        console.print(f"[dim]Parsing: {playlist_name}[/dim]")
        metadata = parser.parse_playlist_name(playlist_name)

        # Determine event type
        event_type = sync_service._get_event_type(metadata)
        if not event_type:
            logger.warning(f"Could not determine event type for: {playlist_name}")
            continue

        event_name = metadata.playlist_name

        # Create event tag
        event_tag = sync_service.mytag_manager.create_or_get_tag(event_name, event_type)

        # Create intelligent playlist for this event
        sync_service._create_event_intelligent_playlist(
            event_type, event_name, event_tag
        )

        playlist_mapping[playlist_name] = {
            "metadata": metadata,
            "type": "event",
            "event_type": event_type,
            "event_tag_id": event_tag.ID,
            "folder_path": str(sync_service.mp3_playlists_root / playlist_name),
        }

    # Commit event playlist structures
    if event_playlists:
        db.commit()
        console.print(
            f"[green]✓ Created {len(event_playlists)} "
            "event playlist structures[/green]"
        )

    return playlist_mapping


def _tag_all_tracks(
    playlist_mapping: Dict[str, Dict[str, Any]],
    sync_service: TrackTagSyncService,
    db: Any,
) -> None:
    """Phase 2: Tag all tracks based on playlist mapping."""
    from pathlib import Path

    total_playlists = len(playlist_mapping)

    for idx, (playlist_name, info) in enumerate(sorted(playlist_mapping.items()), 1):
        metadata = info["metadata"]

        # Build display name with energy info if available
        display_name = playlist_name
        if metadata.energy_tags:
            energy_str = ", ".join(sorted(metadata.energy_tags))
            display_name = f"{playlist_name} [Energy: {energy_str}]"

        console.print(
            f"\n[cyan]Tagging tracks: {display_name} "
            f"({idx}/{total_playlists})[/cyan]"
        )

        try:
            folder_path = Path(info["folder_path"])
            playlist_type = info["type"]

            # Get MP3 tracks
            mp3_tracks = sync_service._scan_mp3_folder(folder_path)

            if not mp3_tracks:
                console.print("[yellow]  ⚠️  No tracks found[/yellow]")
                continue

            added_count, updated_count = _tag_playlist_tracks(
                sync_service, info, metadata, playlist_type, mp3_tracks
            )

            console.print(
                f"[green]  ✅ Added: {added_count}, Updated: {updated_count}[/green]"
            )

            # Commit after each playlist
            db.commit()

        except Exception as e:
            console.print(f"[red]  ❌ Error: {e}[/red]")
            logger.error(
                f"Failed to tag tracks for {playlist_name}: {e}", exc_info=True
            )
            db.rollback()
            # Clear caches after rollback
            sync_service._events_folder_cache.clear()
            if sync_service.structure_service:
                sync_service.structure_service._folder_cache.clear()


def _tag_playlist_tracks(
    sync_service: TrackTagSyncService,
    info: Dict[str, Any],
    metadata: Any,
    playlist_type: str,
    mp3_tracks: List[Path],
) -> tuple[int, int]:
    """Tag tracks for a single playlist.

    Returns:
        Tuple of (added_count, updated_count)
    """
    added_count = 0
    updated_count = 0

    if playlist_type == "genre":
        # Build actual tags for genre playlists
        actual_tags = sync_service._build_actual_tags(metadata)

        # Tag each track
        for mp3_path in mp3_tracks:
            was_added = sync_service._add_or_update_track(mp3_path, actual_tags)
            if was_added:
                added_count += 1
            else:
                updated_count += 1

    elif playlist_type == "event":
        # Build event tags
        event_type = info["event_type"]
        event_name = metadata.playlist_name
        event_tags = {event_type: {event_name}}

        # Tag each track
        for mp3_path in mp3_tracks:
            was_added = sync_service._add_or_update_track(mp3_path, event_tags)
            if was_added:
                added_count += 1
            else:
                updated_count += 1

    return added_count, updated_count


def _process_genre_playlists(
    genre_playlists: list[str], sync_service: TrackTagSyncService, db: Any
) -> None:
    """Process genre playlists (creates intelligent playlists on-demand)."""
    if not genre_playlists:
        return

    console.print(
        "[cyan]📝 Processing genre playlists and creating "
        "intelligent playlists on-demand...[/cyan]"
    )

    for idx, playlist_name in enumerate(sorted(genre_playlists), 1):
        console.print(f"\n[cyan]Processing: {playlist_name}[/cyan]")
        try:
            result = sync_service.sync_playlist(playlist_name)
            _display_event_sync_result(result, compact=True)

            # Commit after each playlist to prevent stale data issues
            db.commit()
            logger.debug(f"Committed playlist {idx}/{len(genre_playlists)}")
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            logger.error(f"Failed to process playlist {playlist_name}: {e}")
            db.rollback()
            # Clear caches after rollback
            sync_service._events_folder_cache.clear()
            if sync_service.structure_service:
                sync_service.structure_service._folder_cache.clear()


def _process_event_playlists(
    event_playlists: list[str], sync_service: TrackTagSyncService, db: Any
) -> None:
    """Process event playlists and create event intelligent playlists."""
    if not event_playlists:
        return

    console.print("\n[cyan]🎉 Processing event playlists...[/cyan]")

    for idx, playlist_name in enumerate(sorted(event_playlists), 1):
        console.print(f"\n[cyan]Processing: {playlist_name}[/cyan]")
        try:
            result = sync_service.sync_playlist(playlist_name)
            _display_event_sync_result(result, compact=True)

            # Commit after each event playlist to prevent stale data issues
            db.commit()
            logger.debug(f"Committed event playlist {idx}/{len(event_playlists)}")
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            logger.error(f"Failed to process event playlist {playlist_name}: {e}")
            db.rollback()
            # Clear caches after rollback
            sync_service._events_folder_cache.clear()
            if sync_service.structure_service:
                sync_service.structure_service._folder_cache.clear()


def _display_event_sync_result(result: Dict[str, Any], compact: bool = False) -> None:
    """Display event sync results."""
    if compact:
        # Compact display for batch sync
        status = "✅"
        if result.get("skipped"):
            status = "⚠️ (skipped)"

        console.print(
            f"  {status} Added: {result['tracks_added']}, "
            f"Updated: {result['tracks_updated']}"
        )
    else:
        console.print("\n[bold green]✅ Sync completed![/bold green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="green", justify="right")

        table.add_row("Playlist Name", result["playlist_name"])
        table.add_row("Tracks Added", str(result["tracks_added"]))
        table.add_row("Tracks Updated", str(result["tracks_updated"]))
        table.add_row("Tags Removed", str(result["tags_removed"]))
        table.add_row("Skipped", "Yes" if result.get("skipped") else "No")

        if result.get("event_type"):
            table.add_row("Event Type", result["event_type"])
            table.add_row("Event Name", result["event_name"])

        console.print(table)
        console.print()


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
