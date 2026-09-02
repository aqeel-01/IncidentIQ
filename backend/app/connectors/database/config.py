"""Database log connector configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.connectors.database.dialect import (
    SqlDialect,
    validate_qualified_table_name,
    validate_sql_identifier,
)
from app.connectors.types import ConnectorConfig, ConnectorType


class DatabaseConnectorConfig(ConnectorConfig):
    """Configuration for a read-only SQL log connector."""

    connector_type: Literal[ConnectorType.DATABASE] = ConnectorType.DATABASE
    dialect: SqlDialect
    connection_url: str = Field(min_length=1)
    table: str = Field(
        min_length=1,
        description="Target table (optionally schema-qualified)",
    )
    query_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    timestamp_column: str = "timestamp"
    message_column: str = "message"
    service_column: str = "service"
    severity_column: str = "severity"
    environment_column: str | None = "environment"
    host_column: str | None = "host"
    request_id_column: str | None = "request_id"
    trace_id_column: str | None = "trace_id"
    id_column: str | None = "id"
    default_service: str | None = None
    default_environment: str | None = None

    @field_validator("table")
    @classmethod
    def _validate_table(cls, value: str) -> str:
        return validate_qualified_table_name(value)

    @field_validator(
        "timestamp_column",
        "message_column",
        "service_column",
        "severity_column",
    )
    @classmethod
    def _validate_required_columns(cls, value: str) -> str:
        return validate_sql_identifier(value, label="column name")

    @field_validator(
        "environment_column",
        "host_column",
        "request_id_column",
        "trace_id_column",
        "id_column",
    )
    @classmethod
    def _validate_optional_columns(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_sql_identifier(value, label="column name")
