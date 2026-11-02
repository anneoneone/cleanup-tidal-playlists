"""Database engine, sessions and schema migrations."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, pool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class DatabaseError(RuntimeError):
    """Raised when the database cannot be opened or upgraded."""


def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


class Database:
    """Cratekeeper's SQLite database.

    Sessions do not expire objects on commit, so rows read in one unit of work can be
    used after it ends (read-only).
    """

    def __init__(self, path: Path) -> None:
        """Create the engine for ``path``.

        Call :meth:`prepare` before use.
        """
        self.path = path
        self.engine: Engine = create_engine(f"sqlite:///{path}")
        event.listen(self.engine, "connect", _set_sqlite_pragmas)
        self._sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Open a unit of work that commits on success and rolls back on error."""
        session = self._sessionmaker()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def prepare(self) -> None:
        """Create a new database, or upgrade an existing one to the latest schema."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if _has_tables(self.path):
            upgrade_schema(self.path)
        else:
            Base.metadata.create_all(self.engine)
            _stamp_head(self.engine)
            logger.info("Created database %s", self.path)

    def schema_revision(self) -> str | None:
        """Return the migration revision stored in the database."""
        with self.engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()

    def dispose(self) -> None:
        """Close all pooled connections (needed before replacing the file)."""
        self.engine.dispose()


def head_revision() -> str:
    """Return the newest migration revision shipped with Cratekeeper."""
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    if head is None:
        raise DatabaseError("No migrations found")
    return head


def upgrade_schema(path: Path) -> None:
    """Run pending migrations on an existing database.

    Foreign keys are off while migrating: SQLite table rebuilds would otherwise
    cascade deletes. Integrity is checked afterwards.
    """
    engine = create_engine(f"sqlite:///{path}", poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            current = MigrationContext.configure(conn).get_current_revision()
            if current is None:
                raise DatabaseError(
                    f"{path} has tables but no migration version. "
                    "Use 'cratekeeper migrate' to import a v1 database."
                )
            if current == head_revision():
                return
            config = _alembic_config()
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
            conn.commit()
            problems = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if problems:
                raise DatabaseError(f"Foreign key check failed: {problems[:5]}")
            logger.info("Upgraded database %s from %s to head", path, current)
    finally:
        engine.dispose()


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def _stamp_head(engine: Engine) -> None:
    with engine.connect() as conn:
        config = _alembic_config()
        config.attributes["connection"] = conn
        command.stamp(config, "head")
        conn.commit()


def _has_tables(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with closing(sqlite3.connect(path)) as conn:
            row = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise DatabaseError(f"{path} is not a SQLite database: {exc}") from exc
    return bool(row and row[0])


def table_names(engine: Engine) -> list[str]:
    """Return the table names in the database (for checks and tests)."""
    return sorted(inspect(engine).get_table_names())
