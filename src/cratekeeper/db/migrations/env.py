"""Alembic environment for Cratekeeper.

The caller passes an open connection in ``config.attributes["connection"]``
(see ``cratekeeper.db.engine``). For autogenerate during development, set
``sqlalchemy.url`` instead. This file never reads user settings and never
configures logging, so it cannot touch a real database by accident.
"""

from alembic import context
from sqlalchemy import create_engine, pool

from cratekeeper.db.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No connection given and sqlalchemy.url is not set")
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported")
run_migrations_online()
