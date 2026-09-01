"""Alembic migration environment (async).

The database URL and target metadata are sourced from the application itself:

- URL comes from ``app.core.config`` (environment / ``.env``), so migrations use
  the same configuration as the running service and no secrets live in
  ``alembic.ini``.
- ``target_metadata`` is ``app.db.base.Base.metadata``. Model modules must be
  imported here as they are added so autogenerate can see them.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import make_async_url

# Import model modules here so their tables register on Base.metadata, e.g.:
#   import app.db.models  # noqa: F401
# No application models exist yet.

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return make_async_url(get_settings().database_url)


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL)."""

    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database using an async engine."""

    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
