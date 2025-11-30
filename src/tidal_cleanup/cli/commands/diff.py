"""Diff command for showing synchronization status.

This module provides the diff command that:
1. Fetches current state from each service (Tidal, Local, Rekordbox)
2. Updates database with locality information
3. Shows diffs for tracks that need synchronization
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import click
from rich.console import Console
from rich.table import Table

from ...config import Config
from ...core.filesystem import FilesystemScanner
from ...core.tidal.snapshot_service import TidalSnapshotService
from ...database import DatabaseService
from ...database.models import Playlist, PlaylistTrack, Track
from ...utils.logging_config import set_log_level
from .init import init

if TYPE_CHECKING:
    from ...core.rekordbox.service import RekordboxService
    from ...core.tidal.api_client import TidalApiService

console = Console()
logger = logging.getLogger(__name__)


def fetch_tidal_state(
    db_service: DatabaseService,
    tidal_service: "TidalApiService",
    playlist_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch current state from Tidal API using TidalSnapshotService.

    Args:
        db_service: Database service
        tidal_service: Tidal API service
        playlist_name: Optional playlist name to filter sync

    Returns:
        Dictionary with fetch statistics
    """
    console.print("[cyan]Fetching from Tidal...[/cyan]")

    # Reset in_tidal flags (filtered by playlist if specified)
    db_service.clear_playlist_track_flag("in_tidal", playlist_name=playlist_name)

    # Use TidalSnapshotService to sync Tidal state to database
    logger.debug(f"Starting Tidal sync (playlist_filter: {playlist_name or 'None'})")
    snapshot_service = TidalSnapshotService(tidal_service, db_service)
    sync_result = snapshot_service.sync_tidal_to_db(playlist_name=playlist_name)

    # Extract statistics
    sync_state = sync_result["sync_state"]
    changes_detected = sync_result["changes_detected"]
    changes_applied = sync_result["changes_applied"]

    logger.debug(
        f"Tidal sync complete: {changes_detected} changes detected, "
        f"{sum(changes_applied.values())} applied"
    )
    logger.debug(f"Changes by type: {changes_applied}")

    console.print(
        f"  [green]✓ Synced {sync_state['counts']['tidal_playlists']} playlists "
        f"with {sync_state['counts']['tidal_tracks']} tracks[/green]"
    )

    if changes_detected > 0:
        console.print(
            f"  [green]✓ Applied {sum(changes_applied.values())} changes "
            f"({changes_detected} detected)[/green]"
        )

    return {
        "playlists_synced": sync_state["counts"]["tidal_playlists"],
        "tracks_synced": sync_state["counts"]["tidal_tracks"],
        "changes_detected": changes_detected,
        "changes_applied": sum(changes_applied.values()),
    }


def fetch_local_state(
    config: Config, db_service: DatabaseService, playlist_name: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch current state from local filesystem.

    Args:
        config: Application configuration
        db_service: Database service
        playlist_name: Optional playlist name to filter scan

    Returns:
        Dictionary with scan statistics
    """
    console.print("[cyan]Scanning local filesystem...[/cyan]")

    # Reset in_local flags (filtered by playlist if specified)
    db_service.clear_playlist_track_flag("in_local", playlist_name=playlist_name)

    playlists_root = Path(config.mp3_directory) / "Playlists"

    if not playlists_root.exists():
        console.print(f"  [yellow]⚠ Directory not found: {playlists_root}[/yellow]")
        return {"playlists_scanned": 0, "files_found": 0}

    scanner = FilesystemScanner(db_service, playlists_root=playlists_root)

    # Scan specific playlist or all playlists
    if playlist_name:
        logger.debug(f"Scanning only playlist: {playlist_name}")
        stats = scanner.scan_playlist(playlist_name)
    else:
        logger.debug("Scanning all playlists")
        stats = scanner.scan_all_playlists()

    # Mark all playlist_tracks as in_local=True for tracks found locally
    # The scanner already updates file_path, so we check that
    marked_count = 0
    with db_service.get_session() as session:
        # Get all playlist tracks where the track has a valid file_path
        from sqlalchemy import select

        stmt = select(PlaylistTrack).join(Track).where(Track.file_path.isnot(None))

        # Filter by playlist if specified
        if playlist_name:
            playlist_obj = (
                session.query(Playlist).filter(Playlist.name == playlist_name).first()
            )
            if playlist_obj:
                stmt = stmt.where(PlaylistTrack.playlist_id == playlist_obj.id)

        playlist_tracks = session.execute(stmt).scalars().all()

        # Mark them as in_local
        for pt in playlist_tracks:
            if not pt.in_local:
                pt.in_local = True
                marked_count += 1

        session.commit()
        logger.debug(f"Marked {marked_count} playlist tracks as in_local")

    console.print(
        f"  [green]✓ Scanned {stats['playlists_scanned']} playlists "
        f"with {stats['files_found']} files[/green]"
    )
    console.print(
        f"  [green]✓ Marked {marked_count} playlist tracks as in_local[/green]"
    )

    return stats


def fetch_rekordbox_state(
    db_service: DatabaseService, rekordbox_service: Optional["RekordboxService"]
) -> Dict[str, Any]:
    """Fetch current state from Rekordbox database.

    Args:
        db_service: Database service
        rekordbox_service: Rekordbox service (may be None)

    Returns:
        Dictionary with Rekordbox statistics
    """
    console.print("[cyan]Checking Rekordbox database...[/cyan]")

    # Reset all in_rekordbox flags to False before checking
    db_service.clear_playlist_track_flag("in_rekordbox")

    if rekordbox_service is None:
        console.print("  [yellow]⚠ Rekordbox database not available[/yellow]")
        return {"available": False, "tracks_count": 0}

    try:
        db = rekordbox_service.db

        if db is None:
            console.print("  [yellow]⚠ Rekordbox database not available[/yellow]")
            return {"available": False, "tracks_count": 0}

        content_count = db.get_content().count()

        # Mark playlist tracks that have rekordbox_content_id as in_rekordbox
        marked_count = 0
        with db_service.get_session() as session:
            from sqlalchemy import select

            stmt = (
                select(PlaylistTrack)
                .join(Track)
                .where(Track.rekordbox_content_id.isnot(None))
            )
            playlist_tracks = session.execute(stmt).scalars().all()

            for pt in playlist_tracks:
                if not pt.in_rekordbox:
                    pt.in_rekordbox = True
                    marked_count += 1

            session.commit()

        console.print(f"  [green]✓ Found {content_count} tracks in Rekordbox[/green]")
        console.print(
            f"  [green]✓ Marked {marked_count} playlist tracks as "
            "in_rekordbox[/green]"
        )

        return {"available": True, "tracks_count": content_count}

    except Exception as e:
        logger.exception("Failed to check Rekordbox")
        console.print(f"  [yellow]⚠ Rekordbox check failed: {e}[/yellow]")
        return {"available": False, "tracks_count": 0, "error": str(e)}


def compute_diff_status(
    playlist_track: PlaylistTrack, exclude_services: Set[str]
) -> Dict[str, Any]:
    """Compute sync status for a playlist track.

    Args:
        playlist_track: PlaylistTrack to analyze
        exclude_services: Set of service names to exclude

    Returns:
        Dictionary with locality information and sync status
    """
    # Get locality flags from PlaylistTrack and explicitly convert to bool
    # to handle SQLite integer (0/1) to Python bool conversion
    in_tidal: Optional[bool] = bool(playlist_track.in_tidal)
    in_local: Optional[bool] = bool(playlist_track.in_local)
    in_rekordbox: Optional[bool] = bool(playlist_track.in_rekordbox)

    # Apply exclusions
    if "tidal" in exclude_services:
        in_tidal = None
    if "local" in exclude_services:
        in_local = None
    if "rekordbox" in exclude_services:
        in_rekordbox = None

    # Determine sync status
    localities = [in_tidal, in_local, in_rekordbox]
    # Remove None (excluded services)
    localities = [loc for loc in localities if loc is not None]

    if not localities:
        has_diff = False
    else:
        # Has diff if not all localities are the same
        has_diff = not all(loc == localities[0] for loc in localities)

    return {
        "in_tidal": in_tidal,
        "in_local": in_local,
        "in_rekordbox": in_rekordbox,
        "has_diff": has_diff,
        "playlist_track": playlist_track,
        "track": playlist_track.track,
    }


def get_tracks_with_diffs(
    db_service: DatabaseService,
    exclude_services: Set[str],
    playlist_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get all playlist tracks that have differences across services.

    Args:
        db_service: Database service
        exclude_services: Set of service names to exclude
        playlist_name: Optional playlist name to filter by

    Returns:
        List of dictionaries with track info and diff status
    """
    from sqlalchemy.orm import joinedload

    with db_service.get_session() as session:
        # Build query with optional playlist filter
        query = session.query(PlaylistTrack).options(joinedload(PlaylistTrack.track))

        if playlist_name:
            # Join with Playlist and filter by name
            query = query.join(Playlist).filter(Playlist.name == playlist_name)

        all_playlist_tracks = query.all()

    tracks_with_diffs = []

    for playlist_track in all_playlist_tracks:
        diff_status = compute_diff_status(playlist_track, exclude_services)

        if diff_status["has_diff"]:
            tracks_with_diffs.append(diff_status)

    return tracks_with_diffs


def get_all_playlist_tracks(
    db_service: DatabaseService, playlist_name: str
) -> List[Dict[str, Any]]:
    """Get all tracks from a specific playlist with their details.

    Args:
        db_service: Database service
        playlist_name: Name of the playlist to fetch tracks from

    Returns:
        List of dictionaries with track info including file paths
    """
    from sqlalchemy.orm import joinedload

    with db_service.get_session() as session:
        # Get the playlist
        playlist_obj = (
            session.query(Playlist).filter(Playlist.name == playlist_name).first()
        )

        if not playlist_obj:
            return []

        # Get all playlist tracks with their associated track data
        query = (
            session.query(PlaylistTrack)
            .options(joinedload(PlaylistTrack.track))
            .filter(PlaylistTrack.playlist_id == playlist_obj.id)
            .order_by(PlaylistTrack.position)
        )

        all_playlist_tracks = query.all()

    tracks_info = []
    for pt in all_playlist_tracks:
        track = pt.track
        tracks_info.append(
            {
                "playlist_track": pt,
                "track": track,
                "in_tidal": bool(pt.in_tidal),
                "in_local": bool(pt.in_local),
                "in_rekordbox": bool(pt.in_rekordbox),
                "file_path": track.file_path or "",
                "position": pt.position,
            }
        )

    return tracks_info


def display_playlist_table(  # noqa: C901
    tracks_info: List[Dict[str, Any]], playlist_name: str, exclude_services: Set[str]
) -> None:
    """Display all tracks in a playlist with their status and file locations.

    Args:
        tracks_info: List of track information dictionaries
        playlist_name: Name of the playlist being displayed
        exclude_services: Set of excluded service names
    """
    if not tracks_info:
        console.print(
            f"\n[yellow]No tracks found in playlist '{playlist_name}'[/yellow]\n"
        )
        return

    console.print(
        f"\n[bold cyan]Playlist: {playlist_name} ({len(tracks_info)} tracks)"
        "[/bold cyan]\n"
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Track", style="cyan", width=40)

    # Add columns for services that aren't excluded
    if "tidal" not in exclude_services:
        table.add_column("Tidal", width=8, justify="center")
    if "local" not in exclude_services:
        table.add_column("Local", width=8, justify="center")
    if "rekordbox" not in exclude_services:
        table.add_column("Rekordbox", width=10, justify="center")

    # Add file path column
    table.add_column("File Path", style="dim", width=60)

    for track_info in tracks_info:
        track = track_info["track"]
        track_name = f"{track.artist} - {track.title}"

        row_data = [str(track_info["position"] or ""), track_name]

        # Add status for each non-excluded service
        if "tidal" not in exclude_services:
            tidal_status = "✓" if track_info["in_tidal"] else "✗"
            tidal_color = "green" if track_info["in_tidal"] else "red"
            row_data.append(f"[{tidal_color}]{tidal_status}[/{tidal_color}]")

        if "local" not in exclude_services:
            local_status = "✓" if track_info["in_local"] else "✗"
            local_color = "green" if track_info["in_local"] else "red"
            row_data.append(f"[{local_color}]{local_status}[/{local_color}]")

        if "rekordbox" not in exclude_services:
            rb_status = "✓" if track_info["in_rekordbox"] else "✗"
            rb_color = "green" if track_info["in_rekordbox"] else "red"
            row_data.append(f"[{rb_color}]{rb_status}[/{rb_color}]")

        # Add file path (show relative path or "Not found")
        file_path = track_info["file_path"]
        if file_path:
            # Shorten path if too long
            if len(file_path) > 57:
                file_path = "..." + file_path[-54:]
            row_data.append(file_path)
        else:
            row_data.append("[red]Not found[/red]")

        table.add_row(*row_data)

    console.print(table)
    console.print()


def display_diff_table(
    tracks_with_diffs: List[Dict[str, Any]], exclude_services: Set[str]
) -> None:
    """Display diff results in a table.

    Args:
        tracks_with_diffs: List of tracks with diff information
        exclude_services: Set of excluded service names
    """
    if not tracks_with_diffs:
        console.print("\n[green]✓ All services are in sync![/green]\n")
        return

    console.print(
        f"\n[bold cyan]Found {len(tracks_with_diffs)} tracks with differences:"
        "[/bold cyan]\n"
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Track", style="cyan", width=40)

    # Add columns for services that aren't excluded
    if "tidal" not in exclude_services:
        table.add_column("Tidal", width=8, justify="center")
    if "local" not in exclude_services:
        table.add_column("Local", width=8, justify="center")
    if "rekordbox" not in exclude_services:
        table.add_column("Rekordbox", width=10, justify="center")

    # Show first 50 tracks
    display_limit = 50
    for diff_info in tracks_with_diffs[:display_limit]:
        track = diff_info["track"]
        track_name = f"{track.artist} - {track.title}"

        row_data = [track_name]

        # Add status for each non-excluded service
        if "tidal" not in exclude_services:
            tidal_status = "✓" if diff_info["in_tidal"] else "✗"
            tidal_color = "green" if diff_info["in_tidal"] else "red"
            row_data.append(f"[{tidal_color}]{tidal_status}[/{tidal_color}]")

        if "local" not in exclude_services:
            local_status = "✓" if diff_info["in_local"] else "✗"
            local_color = "green" if diff_info["in_local"] else "red"
            row_data.append(f"[{local_color}]{local_status}[/{local_color}]")

        if "rekordbox" not in exclude_services:
            rb_status = "✓" if diff_info["in_rekordbox"] else "✗"
            rb_color = "green" if diff_info["in_rekordbox"] else "red"
            row_data.append(f"[{rb_color}]{rb_status}[/{rb_color}]")

        table.add_row(*row_data)

    console.print(table)

    if len(tracks_with_diffs) > display_limit:
        console.print(
            f"\n[yellow]Showing first {display_limit} of "
            f"{len(tracks_with_diffs)} tracks with differences[/yellow]\n"
        )


@click.command("diff")
@click.option(
    "--exclude",
    multiple=True,
    type=click.Choice(["tidal", "local", "rekordbox"], case_sensitive=False),
    help="Exclude a service from diff (can be used multiple times)",
)
@click.option(
    "--playlist",
    "-p",
    type=str,
    help="Filter diff to show only tracks from a specific playlist",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Set logging level (default: INFO)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed information",
)
def diff_command(  # noqa: C901
    exclude: tuple[str, ...], playlist: str, log_level: str, verbose: bool
) -> None:
    r"""Show synchronization status across services.

    This command fetches the current state from each service and displays
    which tracks are present or missing in each location:

    \b
    - Tidal: Tracks in your Tidal playlists
    - Local: Files in your local music directory
    - Rekordbox: Tracks in Rekordbox database

    Tracks that differ across services are highlighted for easy review.

    Examples:
        tidal-cleanup diff
        tidal-cleanup diff --exclude rekordbox
        tidal-cleanup diff --skip-fetch
        tidal-cleanup diff --playlist "My Playlist"
        tidal-cleanup diff --exclude local --exclude rekordbox
    """
    # Set log level using centralized function
    set_log_level(log_level)

    console.print("\n[bold cyan]🔄 Computing Synchronization Status[/bold cyan]\n")

    try:
        config = Config()

        # Initialize all services
        console.print("[cyan]Initializing services...[/cyan]")
        db_service, tidal_service, _download_service, rekordbox_service = init(config)
        console.print("  [green]✓ All services initialized[/green]\n")

        exclude_services = {s.lower() for s in exclude}

        # Fetch from services
        console.print("[bold]Fetching from services...[/bold]\n")

        if "tidal" not in exclude_services:
            fetch_tidal_state(db_service, tidal_service, playlist_name=playlist)

        if "local" not in exclude_services:
            fetch_local_state(config, db_service, playlist_name=playlist)

        if "rekordbox" not in exclude_services:
            fetch_rekordbox_state(db_service, rekordbox_service)

        console.print()

        # Validate playlist if specified
        if playlist:
            with db_service.get_session() as session:
                playlist_obj = (
                    session.query(Playlist).filter(Playlist.name == playlist).first()
                )
                if not playlist_obj:
                    console.print(f"\n[red]✗ Playlist '{playlist}' not found[/red]\n")
                    raise click.ClickException(f"Playlist '{playlist}' not found")
            console.print(f"[cyan]Filtering by playlist: {playlist}[/cyan]\n")

        # Display results based on whether playlist filter is used
        if playlist:
            # Show all tracks in the playlist with file paths
            console.print("[cyan]Fetching playlist tracks...[/cyan]")
            all_tracks = get_all_playlist_tracks(db_service, playlist)
            console.print(f"  [green]✓ Found {len(all_tracks)} tracks[/green]\n")
            display_playlist_table(all_tracks, playlist, exclude_services)
        else:
            # Show only tracks with differences (original behavior)
            console.print("[cyan]Computing differences...[/cyan]")
            tracks_with_diffs = get_tracks_with_diffs(
                db_service, exclude_services, playlist_name=playlist
            )
            console.print(
                f"  [green]✓ Found {len(tracks_with_diffs)} tracks with differences"
                "[/green]\n"
            )
            display_diff_table(tracks_with_diffs, exclude_services)

        # Show summary
        console.print("\n[bold cyan]📊 Summary[/bold cyan]\n")

        # Get overall stats
        with db_service.get_session() as session:
            total_tracks = session.query(Track).count()

        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green", justify="right")

        summary_table.add_row("Total tracks in database", str(total_tracks))
        summary_table.add_row("Tracks with differences", str(len(tracks_with_diffs)))
        in_sync = total_tracks - len(tracks_with_diffs)
        summary_table.add_row("Tracks in sync", str(in_sync))

        console.print(summary_table)
        console.print()

    except click.ClickException:
        raise
    except Exception as e:
        logger.exception("Diff command failed")
        console.print(f"\n[red]✗ Diff failed: {e}[/red]\n")
        raise click.ClickException(str(e))
