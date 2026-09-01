"""Tests for the database layer: URL normalization, sessions, health.

These use SQLite via ``aiosqlite`` as a lightweight, dependency-free test
database so the session machinery and health check can be exercised without a
running PostgreSQL instance.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.health import check_postgres
from app.db.session import Database, check_connection, get_db, make_async_url

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://u:p@localhost:5432/db",
            "postgresql+asyncpg://u:p@localhost:5432/db",
        ),
        (
            "postgresql+psycopg://u:p@localhost/db",
            "postgresql+asyncpg://u:p@localhost/db",
        ),
        (
            "postgresql+asyncpg://u:p@localhost/db",
            "postgresql+asyncpg://u:p@localhost/db",
        ),
        ("sqlite:///./local.db", "sqlite+aiosqlite:///./local.db"),
        (SQLITE_URL, SQLITE_URL),
    ],
)
def test_make_async_url(given: str, expected: str) -> None:
    assert make_async_url(given) == expected


async def test_check_connection_succeeds() -> None:
    engine = create_async_engine(SQLITE_URL)
    try:
        await check_connection(engine)  # must not raise
    finally:
        await engine.dispose()


async def test_database_session_executes_query() -> None:
    settings = Settings(_env_file=None, database_url=SQLITE_URL)
    db = Database(settings)
    try:
        async with db.sessionmaker() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await db.dispose()


async def test_check_postgres_healthy_with_engine() -> None:
    engine = create_async_engine(SQLITE_URL)
    try:
        result = await check_postgres(engine)
        assert result.healthy is True
        assert result.name == "postgres"
    finally:
        await engine.dispose()


async def test_check_postgres_reports_uninitialized_engine() -> None:
    result = await check_postgres(None)
    assert result.healthy is False
    assert result.required is True
    assert "not initialized" in result.detail


async def test_check_postgres_unavailable_connection() -> None:
    # Port 1 is not a listening PostgreSQL; connection must fail gracefully.
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/db")
    try:
        result = await check_postgres(engine)
        assert result.healthy is False
        assert result.required is True
    finally:
        await engine.dispose()


def test_get_db_dependency_provides_working_session() -> None:
    settings = Settings(_env_file=None, database_url=SQLITE_URL)
    db = Database(settings)
    app = FastAPI()
    app.state.db = db

    @app.get("/_dbtest")
    async def _dbtest(
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> dict[str, int]:
        result = await session.execute(text("SELECT 1"))
        return {"value": result.scalar_one()}

    try:
        with TestClient(app) as test_client:
            response = test_client.get("/_dbtest")
        assert response.status_code == 200
        assert response.json() == {"value": 1}
    finally:
        asyncio.run(db.dispose())
