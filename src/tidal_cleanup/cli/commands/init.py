"""Initialization and preparation command for Tidal cleanup application.

This module provides simple initialization functions that return service instances:
- init_db() -> DatabaseService
- init_tidal_api() -> TidalService
- init_tidal_downloader() -> TidalDownloadService
- init_rekordbox() -> RekordboxService
- init() -> tuple of all services

Services are initialized if not present, or fetched and returned if already initialized.
"""

import logging
from typing import Any, Dict, Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

from ...config import Config
from ...core.rekordbox import RekordboxService
from ...core.tidal import TidalDownloadService, TidalService
from ...database import DatabaseService

console = Console()
logger = logging.getLogger(__name__)


class InitializationError(Exception):
    """Raised when initialization fails."""

    pass


def init_db(config: Optional[Config] = None) -> DatabaseService:
    """Initialize or get DatabaseService instance.

    Args:
        config: Application configuration (creates new if not provided)

    Returns:
        DatabaseService instance

    Raises:
        InitializationError: If database cannot be initialized
    """
    if config is None:
        config = Config()

    try:
        db_service = DatabaseService(db_path=config.database_path)

        # Initialize if needed
        if not db_service.is_initialized():
            logger.info("Initializing database schema...")
            db_service.init_db()

        # Verify connection works
        stats = db_service.get_statistics()
        logger.debug(
            f"Database connected: {stats['tracks']} tracks, "
            f"{stats['playlists']} playlists"
        )

        return db_service

    except Exception as e:
        logger.exception("Database initialization failed")
        raise InitializationError(f"Database initialization failed: {e}")


def init_tidal_api(config: Optional[Config] = None) -> TidalService:
    """Initialize or get TidalService instance.

    Args:
        config: Application configuration (creates new if not provided)

    Returns:
        TidalService instance

    Raises:
        InitializationError: If Tidal API authentication fails
    """
    if config is None:
        config = Config()

    try:
        tidal_service = TidalService(config.tidal_token_file)

        # Authenticate if needed
        if not tidal_service.is_authenticated():
            logger.info("Authenticating with Tidal API...")
            tidal_service.connect()

        # Verify connection works
        playlists = tidal_service.get_playlists()
        logger.debug(f"Tidal API connected: {len(playlists)} playlists")

        return tidal_service

    except Exception as e:
        logger.exception("Tidal API initialization failed")
        raise InitializationError(f"Tidal API initialization failed: {e}")


def init_tidal_downloader(config: Optional[Config] = None) -> TidalDownloadService:
    """Initialize or get TidalDownloadService instance.

    Args:
        config: Application configuration (creates new if not provided)

    Returns:
        TidalDownloadService instance

    Raises:
        InitializationError: If Tidal downloader setup fails
    """
    if config is None:
        config = Config()

    try:
        download_service = TidalDownloadService(config)

        # Authenticate if needed
        if not download_service.is_authenticated():
            logger.info("Authenticating Tidal downloader...")
            download_service.connect()

        logger.debug(f"Tidal downloader ready: {config.mp3_directory}")

        return download_service

    except Exception as e:
        logger.exception("Tidal downloader initialization failed")
        raise InitializationError(f"Tidal downloader initialization failed: {e}")


def init_rekordbox(config: Optional[Config] = None) -> Optional[RekordboxService]:
    """Initialize or get RekordboxService instance.

    Args:
        config: Application configuration (creates new if not provided)

    Returns:
        RekordboxService instance, or None if not available

    Note:
        Returns None if Rekordbox is not available (non-critical service)
    """
    if config is None:
        config = Config()

    try:
        rekordbox_service = RekordboxService(config=config)

        # Check if database is accessible
        db = rekordbox_service.db
        if db is None:
            logger.warning("Rekordbox database not available")
            return None

        # Get basic info
        content_count = db.get_content().count()
        logger.debug(f"Rekordbox connected: {content_count} tracks")

        return rekordbox_service

    except Exception as e:
        logger.warning(f"Rekordbox initialization failed: {e}")
        return None


def init(
    config: Optional[Config] = None,
) -> Tuple[
    DatabaseService, TidalService, TidalDownloadService, Optional[RekordboxService]
]:
    """Initialize all services and return instances.

    Args:
        config: Application configuration (creates new if not provided)

    Returns:
        Tuple of (DatabaseService, TidalService, TidalDownloadService, RekordboxService)
        Note: RekordboxService may be None if not available

    Raises:
        InitializationError: If any critical service fails to initialize
    """
    if config is None:
        config = Config()

    try:
        # Initialize all services
        db_service = init_db(config)
        tidal_service = init_tidal_api(config)
        download_service = init_tidal_downloader(config)
        rekordbox_service = init_rekordbox(config)

        logger.info("All services initialized successfully")

        return db_service, tidal_service, download_service, rekordbox_service

    except InitializationError:
        raise
    except Exception as e:
        logger.exception("Service initialization failed")
        raise InitializationError(f"Service initialization failed: {e}")


def check_database_connection(config: Config) -> Dict[str, Any]:
    """Check database connection and initialize if needed.

    Args:
        config: Application configuration

    Returns:
        Dictionary with status and details

    Raises:
        InitializationError: If database cannot be initialized
    """
    try:
        console.print("[cyan]Checking database connection...[/cyan]")
        db_service = init_db(config)
        stats = db_service.get_statistics()

        return {
            "status": "success",
            "message": "Database connected",
            "details": {
                "path": str(db_service.db_path),
                "tracks": stats["tracks"],
                "playlists": stats["playlists"],
            },
        }

    except Exception as e:
        logger.exception("Database check failed")
        raise InitializationError(f"Database connection failed: {e}")


def check_tidal_api_connection(config: Config) -> Dict[str, Any]:
    """Check Tidal API connection and authenticate if needed.

    Args:
        config: Application configuration

    Returns:
        Dictionary with status and details

    Raises:
        InitializationError: If authentication fails
    """
    try:
        console.print("[cyan]Checking Tidal API connection...[/cyan]")
        tidal_service = init_tidal_api(config)
        playlists = tidal_service.get_playlists()

        return {
            "status": "success",
            "message": "Tidal API connected",
            "details": {
                "token_file": str(config.tidal_token_file),
                "authenticated": True,
                "playlists_count": len(playlists),
            },
        }

    except Exception as e:
        logger.exception("Tidal API check failed")
        raise InitializationError(f"Tidal API connection failed: {e}")


def check_tidal_downloader_connection(config: Config) -> Dict[str, Any]:
    """Check Tidal downloader setup and authenticate if needed.

    Args:
        config: Application configuration

    Returns:
        Dictionary with status and details

    Raises:
        InitializationError: If downloader setup fails
    """
    try:
        console.print("[cyan]Checking Tidal downloader setup...[/cyan]")
        _ = init_tidal_downloader(config)

        return {
            "status": "success",
            "message": "Tidal downloader ready",
            "details": {
                "authenticated": True,
                "download_directory": str(config.mp3_directory),
            },
        }

    except Exception as e:
        logger.exception("Tidal downloader check failed")
        raise InitializationError(f"Tidal downloader setup failed: {e}")


def check_rekordbox_connection(config: Config) -> Dict[str, Any]:
    """Check Rekordbox database connection.

    Args:
        config: Application configuration

    Returns:
        Dictionary with status and details

    Note:
        Returns a warning if pyrekordbox is not available, but doesn't fail
    """
    try:
        console.print("[cyan]Checking Rekordbox database connection...[/cyan]")
        rekordbox_service = init_rekordbox(config)

        if rekordbox_service is None:
            console.print(
                "  [yellow]Warning: pyrekordbox not available "
                "or database not accessible[/yellow]"
            )
            return {
                "status": "warning",
                "message": "Rekordbox database not available",
                "details": {
                    "available": False,
                    "note": "Install pyrekordbox for Rekordbox integration",
                },
            }

        # Get basic info
        db = rekordbox_service.db
        if db is None:
            raise InitializationError("Rekordbox database not available")
        property_info = db.get_property().first()
        content_count = db.get_content().count()

        return {
            "status": "success",
            "message": "Rekordbox database connected",
            "details": {
                "available": True,
                "tracks_count": content_count,
                "db_version": (
                    getattr(property_info, "DBVersion", "unknown")
                    if property_info
                    else "unknown"
                ),
            },
        }

    except Exception as e:
        logger.exception("Rekordbox database check failed")
        console.print(
            f"  [yellow]Warning: Could not connect to Rekordbox database: {e}[/yellow]"
        )
        return {
            "status": "warning",
            "message": "Rekordbox database connection failed",
            "details": {
                "available": False,
                "error": str(e),
            },
        }


def check_all_services(
    config: Optional[Config] = None, skip_rekordbox: bool = False
) -> Dict[str, Any]:
    """Run all initialization checks.

    Args:
        config: Application configuration (creates new if not provided)
        skip_rekordbox: Whether to skip Rekordbox check

    Returns:
        Dictionary with results from all checks

    Raises:
        InitializationError: If any critical service fails to initialize
    """
    if config is None:
        config = Config()

    results = {}

    try:
        # Database (critical)
        results["database"] = check_database_connection(config)
        console.print("  [green]✓ Database OK[/green]\n")

        # Tidal API (critical)
        results["tidal_api"] = check_tidal_api_connection(config)
        console.print("  [green]✓ Tidal API OK[/green]\n")

        # Tidal Downloader (critical)
        results["tidal_downloader"] = check_tidal_downloader_connection(config)
        console.print("  [green]✓ Tidal Downloader OK[/green]\n")

        # Rekordbox (optional)
        if not skip_rekordbox:
            results["rekordbox"] = check_rekordbox_connection(config)
            if results["rekordbox"]["status"] == "success":
                console.print("  [green]✓ Rekordbox OK[/green]\n")
            else:
                console.print("  [yellow]⚠ Rekordbox unavailable (optional)[/yellow]\n")
        else:
            results["rekordbox"] = {
                "status": "skipped",
                "message": "Rekordbox check skipped",
                "details": {},
            }

        # Check if all critical services are ready
        all_ready = all(
            results[key]["status"] == "success"
            for key in ["database", "tidal_api", "tidal_downloader"]
        )

        results["all_ready"] = {"ready": all_ready}

        return results

    except InitializationError:
        raise
    except Exception as e:
        logger.exception("Initialization check failed")
        raise InitializationError(f"Initialization failed: {e}")


def _display_results_table(results: Dict[str, Any], skip_rekordbox: bool) -> None:
    """Display results in a formatted table.

    Args:
        results: Results dictionary from check_all_services
        skip_rekordbox: Whether Rekordbox was skipped
    """
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Service", style="cyan", width=20)
    table.add_column("Status", width=15)
    table.add_column("Details", style="dim")

    # Database
    db_result = results["database"]
    status_icon = "✓" if db_result["status"] == "success" else "✗"
    status_color = "green" if db_result["status"] == "success" else "red"
    db_tracks = db_result["details"]["tracks"]
    db_playlists = db_result["details"]["playlists"]
    details = f"Tracks: {db_tracks}, Playlists: {db_playlists}"
    table.add_row(
        "Database",
        f"[{status_color}]{status_icon} {db_result['status']}[/{status_color}]",
        details,
    )

    # Tidal API
    api_result = results["tidal_api"]
    status_icon = "✓" if api_result["status"] == "success" else "✗"
    status_color = "green" if api_result["status"] == "success" else "red"
    details = f"Playlists: {api_result['details']['playlists_count']}"
    table.add_row(
        "Tidal API",
        f"[{status_color}]{status_icon} {api_result['status']}[/{status_color}]",
        details,
    )

    # Tidal Downloader
    dl_result = results["tidal_downloader"]
    status_icon = "✓" if dl_result["status"] == "success" else "✗"
    status_color = "green" if dl_result["status"] == "success" else "red"
    details = f"Dir: {dl_result['details']['download_directory']}"
    table.add_row(
        "Tidal Downloader",
        f"[{status_color}]{status_icon} {dl_result['status']}[/{status_color}]",
        details,
    )

    # Rekordbox
    if not skip_rekordbox:
        rb_result = results["rekordbox"]
        if rb_result["status"] == "success":
            status_icon = "✓"
            status_color = "green"
            details = f"Tracks: {rb_result['details']['tracks_count']}"
        elif rb_result["status"] == "warning":
            status_icon = "⚠"
            status_color = "yellow"
            details = rb_result["details"].get("note", "Not available")
        else:
            status_icon = "✗"
            status_color = "red"
            details = "Failed"
        table.add_row(
            "Rekordbox",
            f"[{status_color}]{status_icon} {rb_result['status']}[/{status_color}]",
            details,
        )

    console.print(table)


@click.command("init")
@click.option(
    "--skip-rekordbox",
    is_flag=True,
    help="Skip Rekordbox database check (optional service)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed information",
)
def init_command(skip_rekordbox: bool, verbose: bool) -> None:  # noqa: C901
    r"""Initialize and check all services.

    This command checks that all required services are properly configured
    and authenticated:

    \b
    - Database: Connection and schema
    - Tidal API: OAuth authentication
    - Tidal Downloader: Download service setup
    - Rekordbox: Database connection (optional)

    If any service is not set up, it will be initialized interactively.

    Examples:
        tidal-cleanup init
        tidal-cleanup init --skip-rekordbox
        tidal-cleanup init -v
    """
    console.print("\n[bold cyan]🔧 Initializing Services[/bold cyan]\n")

    try:
        config = Config()
        results = check_all_services(config, skip_rekordbox=skip_rekordbox)

        # Display summary table
        console.print("\n[bold cyan]📊 Initialization Summary[/bold cyan]\n")
        _display_results_table(results, skip_rekordbox)

        # Final status
        if results["all_ready"]:
            console.print(
                "\n[bold green]✓ All services initialized successfully!"
                "[/bold green]\n"
            )
        else:
            console.print(
                "\n[bold red]✗ Some services failed to initialize[/bold red]\n"
            )
            raise click.ClickException("Initialization incomplete")

        # Show verbose details if requested
        if verbose:
            console.print("\n[bold]Detailed Information:[/bold]\n")
            for service_name, result in results.items():
                if service_name == "all_ready":
                    continue
                console.print(f"[cyan]{service_name.upper()}:[/cyan]")
                console.print(f"  Message: {result['message']}")
                if result.get("details"):
                    for key, value in result["details"].items():
                        console.print(f"  {key}: {value}")
                console.print()

    except InitializationError as e:
        console.print(f"\n[red]✗ Initialization failed: {e}[/red]\n")
        raise click.ClickException(str(e))
    except Exception as e:
        logger.exception("Unexpected error during initialization")
        console.print(f"\n[red]✗ Unexpected error: {e}[/red]\n")
        raise click.ClickException(str(e))
