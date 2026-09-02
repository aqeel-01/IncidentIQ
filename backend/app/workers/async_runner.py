"""Async execution helpers for Celery workers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

from app.core.config import Settings
from app.db.session import Database

T = TypeVar("T")


def run_async(coro: Coroutine[object, object, T]) -> T:
    """Run an async coroutine from a synchronous Celery task."""

    return asyncio.run(coro)


async def run_with_session(
    settings: Settings,
    handler,
):
    """Open a database session, run ``handler(session, settings)``, and dispose."""

    database = Database(settings)
    try:
        async with database.sessionmaker() as session:
            return await handler(session, settings)
    finally:
        await database.dispose()
