"""Async database engine and session management.

Provides:

- :func:`make_async_url` — normalize a DSN to an async driver.
- :class:`Database` — owns the async engine and session factory; created once
  per application in the lifespan and disposed on shutdown.
- :func:`get_db` — FastAPI dependency yielding a request-scoped
  :class:`AsyncSession` with rollback-on-error and guaranteed close.

Keeping the engine on ``app.state`` (rather than a module global) keeps it tied
to the running application/event loop and makes tests straightforward.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

# Map of sync DSN scheme -> async driver scheme.
_ASYNC_SCHEMES = {
    "postgresql://": "postgresql+asyncpg://",
    "postgresql+psycopg://": "postgresql+asyncpg://",
    "postgresql+psycopg2://": "postgresql+asyncpg://",
    "sqlite://": "sqlite+aiosqlite://",
}


def make_async_url(url: str) -> str:
    """Return ``url`` using an async driver, leaving already-async URLs intact."""

    for prefix in ("postgresql+asyncpg://", "sqlite+aiosqlite://"):
        if url.startswith(prefix):
            return url
    for sync_prefix, async_prefix in _ASYNC_SCHEMES.items():
        if url.startswith(sync_prefix):
            return async_prefix + url[len(sync_prefix) :]
    return url


def create_engine(settings: Settings) -> AsyncEngine:
    """Create an :class:`AsyncEngine` from application settings.

    Engine creation is lazy about connections, so this succeeds even when the
    database is currently unreachable — the app can still start and report
    readiness separately.
    """

    return create_async_engine(
        make_async_url(settings.database_url),
        pool_pre_ping=True,
        future=True,
    )


async def check_connection(engine: AsyncEngine) -> None:
    """Open a connection and run ``SELECT 1``; raises on failure."""

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


class Database:
    """Owns the async engine and session factory for the application lifetime."""

    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_engine(settings)
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session, rolling back on error and always closing."""

    database: Database = request.app.state.db
    session = database.sessionmaker()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
