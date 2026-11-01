"""Command-line interface for the Tidal cleanup application.

This is the main entry point that delegates to command modules.
"""

from pathlib import Path

import click

from ..utils.logging_config import configure_third_party_loggers, setup_logging
from .commands import download, init_command, sync_command


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Set logging level",
)
@click.option("--log-file", type=click.Path(), help="Log to file")
def cli(log_level: str, log_file: str) -> None:
    """Tidal Playlist Cleanup Tool.

    A modern tool for synchronizing Tidal playlists with local audio files.
    """
    # Set up logging
    setup_logging(log_level=log_level, log_file=Path(log_file) if log_file else None)
    configure_third_party_loggers()


# Register command groups and commands
cli.add_command(init_command)
cli.add_command(sync_command)
cli.add_command(download)


if __name__ == "__main__":
    cli()
