"""Logging setup: console, rotating log file, and forwarding into the running job."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.logging import RichHandler

from .jobs import current_context

LOGGER_NAME = "cratekeeper"
FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

QUIET_LOGGERS = (
    "sqlalchemy",
    "alembic",
    "urllib3",
    "requests",
    "httpx",
    "mutagen",
    "tidalapi",
    "tidal_dl_ng",
    "pyrekordbox",
    "uvicorn.access",
)


class JobLogHandler(logging.Handler):
    """Copy Cratekeeper log records into the job running in the same thread."""

    def emit(self, record: logging.LogRecord) -> None:
        """Forward the record if a job runs in this thread."""
        context = current_context()
        if context is None:
            return
        try:
            context.log(record.getMessage(), level=record.levelname.lower())
        except Exception:
            self.handleError(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    console: bool = True,
) -> None:
    """Configure the ``cratekeeper`` logger.

    Safe to call more than once.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    if console:
        logger.addHandler(
            RichHandler(show_path=False, rich_tracebacks=True, markup=False)
        )
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
        logger.addHandler(file_handler)
    job_handler = JobLogHandler()
    job_handler.setLevel(logging.INFO)
    logger.addHandler(job_handler)

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
