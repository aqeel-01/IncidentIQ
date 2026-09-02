"""Tests for the read-only SQL database log connector."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.connectors import (
    ConnectorRegistry,
    ConnectorState,
    ConnectorType,
    default_connector_registry,
)
from app.connectors.database import (
    DatabaseConnector,
    DatabaseConnectorConfig,
    DatabaseNotConnectedError,
    DatabaseReadOnlyError,
    LogQueryFilters,
    SqlDialect,
    build_log_select_query,
    create_database_connector,
    sql_row_to_log_event,
    sql_rows_to_log_events,
    validate_read_only_sql,
)
from app.connectors.database.client import SqlAlchemyDatabaseClient
from app.connectors.database.dialect import normalize_connection_url
from app.connectors.database.query import BuiltLogQuery
from app.db.models.enums import Severity
from app.domain.events import LogEvent


def _config(
    dialect: SqlDialect = SqlDialect.POSTGRESQL,
    **overrides: object,
) -> DatabaseConnectorConfig:
    base: dict[str, object] = {
        "name": "warehouse",
        "dialect": dialect,
        "connection_url": "postgresql://logs:secret@db:5432/logs",
        "table": "application_logs",
        "default_service": "payments-api",
        "default_environment": "production",
    }
    base.update(overrides)
    return DatabaseConnectorConfig(**base)


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, minutes, tzinfo=UTC)


SAMPLE_ROW = {
    "id": 42,
    "timestamp": "2026-09-01T12:00:00Z",
    "message": "connection refused",
    "service": "payments-api",
    "environment": "production",
    "severity": "error",
    "host": "api-1",
}


class MockDatabaseSQLClient:
    """In-memory SQL client for connector tests."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        ping_raises: Exception | None = None,
        fetch_raises: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.ping_raises = ping_raises
        self.fetch_raises = fetch_raises
        self.fetch_calls: list[BuiltLogQuery] = []
        self.ping_calls = 0

    async def fetch_rows(self, query: BuiltLogQuery) -> list[dict[str, Any]]:
        self.fetch_calls.append(query)
        if self.fetch_raises is not None:
            raise self.fetch_raises
        return list(self.rows)

    async def ping(self) -> None:
        self.ping_calls += 1
        if self.ping_raises is not None:
            raise self.ping_raises

    async def aclose(self) -> None:
        return None


@pytest.mark.parametrize(
    ("dialect", "expected_quote"),
    [
        (SqlDialect.POSTGRESQL, '"timestamp"'),
        (SqlDialect.MYSQL, "`timestamp`"),
    ],
)
def test_build_log_select_query_quotes_identifiers_per_dialect(
    dialect: SqlDialect,
    expected_quote: str,
) -> None:
    query = build_log_select_query(
        LogQueryFilters(
            start=_ts(0),
            end=_ts(30),
            service="payments-api",
            environment="production",
            severity=Severity.HIGH,
            size=250,
        ),
        _config(dialect=dialect),
    )

    sql = str(query.statement)
    assert expected_quote in sql
    assert query.params["service"] == "payments-api"
    assert query.params["environment"] == "production"
    assert query.params["limit"] == 250
    assert "severity_0" in query.params


def test_build_log_select_query_supports_schema_qualified_table() -> None:
    query = build_log_select_query(
        LogQueryFilters(start=_ts(0), end=_ts(10)),
        _config(table="logs.application_logs"),
    )

    sql = str(query.statement)
    assert '"logs"."application_logs"' in sql


def test_sql_rows_to_log_events_maps_valid_rows() -> None:
    events = sql_rows_to_log_events(
        [SAMPLE_ROW],
        config=_config(),
        source_name="database:warehouse",
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, LogEvent)
    assert event.message == "connection refused"
    assert event.severity is Severity.HIGH
    assert event.service == "payments-api"
    assert event.source == "database:warehouse"
    assert event.source_type == "database"
    assert event.source_id == "42"
    assert event.raw_data == SAMPLE_ROW


@pytest.mark.parametrize(
    "row",
    [
        {"timestamp": "2026-09-01T12:00:00Z", "message": "", "service": "api"},
        {"timestamp": "2026-09-01T12:00:00Z", "service": "api"},
        {"message": "hello", "service": "api"},
        {"timestamp": "not-a-time", "message": "hello", "service": "api"},
    ],
)
def test_sql_row_to_log_event_skips_invalid_mappings(row: dict[str, object]) -> None:
    event = sql_row_to_log_event(
        row,
        config=_config(),
        source_name="database:warehouse",
    )

    assert event is None


def test_config_rejects_unsafe_column_names() -> None:
    with pytest.raises(ValidationError):
        _config(message_column="message; DROP TABLE logs")


def test_config_rejects_unsafe_table_names() -> None:
    with pytest.raises(ValidationError):
        _config(table="logs; DROP TABLE application_logs")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO logs VALUES (1)",
        "DELETE FROM logs",
        "UPDATE logs SET message = 'x'",
        "DROP TABLE logs",
        "SELECT 1; DELETE FROM logs",
        "SELECT * FROM logs INTO OUTFILE '/tmp/x'",
    ],
)
def test_validate_read_only_sql_rejects_destructive_statements(sql: str) -> None:
    with pytest.raises(DatabaseReadOnlyError):
        validate_read_only_sql(sql)


def test_validate_read_only_sql_allows_select() -> None:
    validate_read_only_sql("SELECT id, message FROM application_logs WHERE id = 1")


@pytest.mark.asyncio
async def test_client_rejects_non_select_before_execution() -> None:
    client = SqlAlchemyDatabaseClient(_config())
    destructive = BuiltLogQuery(
        statement=text("DELETE FROM application_logs"),
        params={},
    )

    with pytest.raises(DatabaseReadOnlyError):
        await client.fetch_rows(destructive)

    await client.aclose()


@pytest.mark.asyncio
async def test_connect_health_and_search_logs_with_mock_client() -> None:
    client = MockDatabaseSQLClient(rows=[SAMPLE_ROW])
    connector = DatabaseConnector(_config(), client=client)

    await connector.connect()
    health = await connector.health_check()
    events = await connector.search_logs(
        LogQueryFilters(start=_ts(0), end=_ts(10), severity=Severity.HIGH)
    )

    assert connector.state is ConnectorState.CONNECTED
    assert health.healthy is True
    assert len(events) == 1
    assert len(client.fetch_calls) == 1
    validate_read_only_sql(str(client.fetch_calls[0].statement))


@pytest.mark.asyncio
async def test_search_logs_without_connect_raises_not_connected() -> None:
    connector = DatabaseConnector(_config())

    with pytest.raises(DatabaseNotConnectedError):
        await connector.search_logs(LogQueryFilters(start=_ts(0), end=_ts(10)))


@pytest.mark.asyncio
async def test_test_connection_uses_ping_without_persistent_session() -> None:
    client = MockDatabaseSQLClient()
    connector = DatabaseConnector(_config(), client=client)

    result = await connector.test_connection()

    assert result.success is True
    assert connector.state is ConnectorState.DISCONNECTED
    assert client.ping_calls == 1


def test_registry_creates_database_connector() -> None:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.DATABASE, create_database_connector)

    connector = registry.create(_config())

    assert isinstance(connector, DatabaseConnector)


def test_default_registry_includes_database_connector() -> None:
    registry = default_connector_registry()
    connector = registry.create(_config())

    assert isinstance(connector, DatabaseConnector)


@pytest.mark.parametrize(
    ("dialect", "url", "expected"),
    [
        (
            SqlDialect.POSTGRESQL,
            "postgresql://user:pass@host/db",
            "postgresql+asyncpg://user:pass@host/db",
        ),
        (
            SqlDialect.MYSQL,
            "mysql://user:pass@host/db",
            "mysql+asyncmy://user:pass@host/db",
        ),
    ],
)
def test_normalize_connection_url_for_supported_dialects(
    dialect: SqlDialect,
    url: str,
    expected: str,
) -> None:
    assert normalize_connection_url(url, dialect) == expected


def test_mysql_config_accepts_custom_column_mappings() -> None:
    config = _config(
        dialect=SqlDialect.MYSQL,
        connection_url="mysql://user:pass@host/logs",
        table="app_logs",
        timestamp_column="logged_at",
        message_column="log_message",
        service_column="app_service",
        severity_column="log_level",
    )

    assert config.timestamp_column == "logged_at"
    assert config.message_column == "log_message"
    assert config.service_column == "app_service"
    assert config.severity_column == "log_level"
