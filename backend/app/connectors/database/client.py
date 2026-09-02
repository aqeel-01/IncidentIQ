"""SQL client for read-only database log access."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.connectors.database.config import DatabaseConnectorConfig
from app.connectors.database.dialect import normalize_connection_url
from app.connectors.database.errors import DatabaseQueryError
from app.connectors.database.query import BuiltLogQuery
from app.connectors.database.read_only import validate_read_only_sql


class DatabaseSQLClient(Protocol):
    """Minimal SQL surface used by :class:`DatabaseConnector`."""

    async def fetch_rows(self, query: BuiltLogQuery) -> list[dict[str, Any]]: ...

    async def ping(self) -> None: ...

    async def aclose(self) -> None: ...


class SqlAlchemyDatabaseClient:
    """Async SQL client backed by SQLAlchemy."""

    def __init__(self, config: DatabaseConnectorConfig) -> None:
        self._config = config
        self._engine: AsyncEngine = create_async_engine(
            normalize_connection_url(config.connection_url, config.dialect),
            pool_pre_ping=True,
            future=True,
        )

    async def fetch_rows(self, query: BuiltLogQuery) -> list[dict[str, Any]]:
        sql = str(query.statement)
        validate_read_only_sql(sql)
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(query.statement, query.params)
                mappings = result.mappings().all()
        except Exception as exc:
            msg = f"database query failed: {exc}"
            raise DatabaseQueryError(msg) from exc
        return [dict(row) for row in mappings]

    async def ping(self) -> None:
        await self.fetch_rows(BuiltLogQuery(statement=text("SELECT 1"), params={}))

    async def aclose(self) -> None:
        await self._engine.dispose()
