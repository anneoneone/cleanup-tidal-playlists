"""Logging configuration for the Tidal cleanup application."""

import logging
import logging.handlers
import sys
import warnings
from pathlib import Path
from typing import Any, Optional


class LocationFormatter(logging.Formatter):
    """Base formatter that adds a combined location field."""

    def format(self, record: Any) -> str:
        """Format log record with combined location field."""
        # Add combined location field
        record.location = f"{record.filename}:{record.lineno}"
        return super().format(record)


class ColoredFormatter(LocationFormatter):
    """Colored log formatter for console output."""

    # Color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record: Any) -> str:
        """Format log record with colors."""
        log_color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset_color = self.COLORS["RESET"]

        # Store original levelname for padding calculation
        original_levelname = record.levelname

        # Add color to level name with proper padding applied before colors
        record.levelname = f"{log_color}{original_levelname:<8}{reset_color}"

        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    console_output: bool = True,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """Set up application logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        console_output: Whether to output logs to console
        max_file_size: Maximum size of log file before rotation
        backup_count: Number of backup log files to keep
    """
    # Suppress deprecation warnings from tidalapi library
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="tidalapi")

    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Set up console logging
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)

        console_formatter = ColoredFormatter(
            fmt=("%(asctime)s - %(location)-30s - " "%(levelname)s - %(message)s"),
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Set up file logging if specified
    if log_file:
        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Use rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_file_size, backupCount=backup_count
        )
        file_handler.setLevel(numeric_level)

        file_formatter = LocationFormatter(
            fmt=("%(asctime)s - %(location)-30s - " "%(levelname)-8s - %(message)s"),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Log initial message
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized - Level: %s", log_level)
    if log_file:
        logger.info("Log file: %s", log_file)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, message: str) -> None:
    """Log an exception with full traceback.

    Args:
        logger: Logger instance
        message: Custom message to log with exception
    """
    logger.exception(message, exc_info=True)


def set_log_level(level: str) -> None:
    """Change the log level for application loggers only.

    Only sets the specified level for tidal_cleanup loggers.
    Third-party loggers remain at INFO or higher to reduce noise.

    Args:
        level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Set root logger level to the minimum needed
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if level.upper() == "DEBUG" else numeric_level)

    # Set all handler levels
    for handler in root_logger.handlers:
        handler.setLevel(numeric_level)

    # Set level only for tidal_cleanup loggers
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("tidal_cleanup"):
            logger = logging.getLogger(name)
            logger.setLevel(numeric_level)

    # Ensure third-party loggers stay quiet
    if level.upper() == "DEBUG":
        configure_third_party_loggers()

    logger = logging.getLogger(__name__)
    logger.debug("Log level changed to: %s (tidal_cleanup loggers only)", level)


# Silence noisy third-party loggers
def configure_third_party_loggers() -> None:
    """Configure third-party library loggers to reduce noise."""
    # Database/SQLAlchemy - silence ALL sqlalchemy loggers
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.base").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.cursor").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    # Mutagen (audio file metadata)
    logging.getLogger("mutagen").setLevel(logging.WARNING)

    # HTTP/Network libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Other common libraries
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    # Tidal libraries
    logging.getLogger("tidalapi").setLevel(logging.WARNING)
    logging.getLogger("tidal_dl_ng").setLevel(logging.WARNING)
