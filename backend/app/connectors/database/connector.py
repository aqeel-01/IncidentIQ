"""Read-only SQL database log connector."""

from __future__ import annotations

from app.connectors.base import Connector
from app.connectors.database.client import DatabaseSQLClient, SqlAlchemyDatabaseClient
from app.connectors.database.config import DatabaseConnectorConfig
from app.connectors.database.convert import sql_rows_to_log_events
from app.connectors.database.errors import (
    DatabaseConnectionError,
    DatabaseNotConnectedError,
    DatabaseQueryError,
)
from app.connectors.database.query import build_log_select_query
from app.connectors.search.types import LogQueryFilters
from app.connectors.types import (
    ConnectionTestResult,
    ConnectorState,
    HealthCheckResult,
)
from app.domain.events import LogEvent


class DatabaseConnector(Connector):
    """Read-only connector for SQL-backed application logs."""

    def __init__(
        self,
        config: DatabaseConnectorConfig,
        *,
        client: DatabaseSQLClient | None = None,
    ) -> None:
        super().__init__(config)
        self._database_config = config
        self._client = client
        self._owns_client = client is None

    @property
    def database_config(self) -> DatabaseConnectorConfig:
        return self._database_config

    def _source(self) -> str:
        return f"database:{self.name}"

    async def connect(self) -> None:
        if self._client is None:
            self._client = SqlAlchemyDatabaseClient(self._database_config)
            self._owns_client = True
        try:
            await self._client.ping()
            self._state = ConnectorState.CONNECTED
        except (DatabaseConnectionError, DatabaseQueryError) as exc:
            self._state = ConnectorState.ERROR
            raise DatabaseConnectionError(str(exc)) from exc

    async def disconnect(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._state = ConnectorState.DISCONNECTED

    async def health_check(self) -> HealthCheckResult:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            return HealthCheckResult(
                connector_type=self.connector_type,
                name=self.name,
                healthy=False,
                state=self.state,
                detail="not connected",
            )

        try:
            await self._client.ping()
            healthy = True
            detail = "ok"
        except (DatabaseConnectionError, DatabaseQueryError) as exc:
            healthy = False
            detail = str(exc)

        return HealthCheckResult(
            connector_type=self.connector_type,
            name=self.name,
            healthy=healthy,
            state=self.state,
            detail=detail,
        )

    async def test_connection(self) -> ConnectionTestResult:
        probe_client = self._client
        created_probe = False
        if probe_client is None:
            probe_client = SqlAlchemyDatabaseClient(self._database_config)
            created_probe = True

        try:
            await probe_client.ping()
            success = True
            detail = "ok"
        except (DatabaseConnectionError, DatabaseQueryError) as exc:
            success = False
            detail = str(exc)
        finally:
            if created_probe:
                await probe_client.aclose()

        return ConnectionTestResult(
            connector_type=self.connector_type,
            name=self.name,
            success=success,
            detail=detail,
        )

    async def search_logs(self, filters: LogQueryFilters) -> list[LogEvent]:
        """Query logs from the configured table and return canonical events."""

        client = self._require_client()
        query = build_log_select_query(filters, self._database_config)
        try:
            rows = await client.fetch_rows(query)
        except DatabaseQueryError:
            raise
        return sql_rows_to_log_events(
            rows,
            config=self._database_config,
            source_name=self._source(),
        )

    def _require_client(self) -> DatabaseSQLClient:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            msg = "database connector is not connected"
            raise DatabaseNotConnectedError(msg)
        return self._client


def create_database_connector(config: DatabaseConnectorConfig) -> DatabaseConnector:
    """Factory used by :class:`~app.connectors.registry.ConnectorRegistry`."""

    return DatabaseConnector(config)
