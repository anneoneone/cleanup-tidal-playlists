"""Command-line interface for the Tidal cleanup application.

This is the main entry point that delegates to command modules.
"""

from pathlib import Path
from typing import Any

import click

from ..utils.logging_config import configure_third_party_loggers, setup_logging
from .commands import (
    TidalCleanupApp,
    db,
    diff_command,
    download,
    init_command,
    legacy_convert,
    legacy_full,
    legacy_sync,
    rekordbox,
    status,
    sync_command,
    sync_rekordbox_command,
)


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


# Register command groups and commands
cli.add_command(init_command)
cli.add_command(diff_command)
cli.add_command(sync_command)
cli.add_command(legacy_sync)
cli.add_command(legacy_convert)
cli.add_command(rekordbox)
cli.add_command(sync_rekordbox_command)
cli.add_command(status)
cli.add_command(legacy_full)
cli.add_command(download)
cli.add_command(db)


if __name__ == "__main__":
    cli()
