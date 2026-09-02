"""Parameterized SELECT builders for database log queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import Any

from sqlalchemy import TextClause, text

from app.connectors.database.config import DatabaseConnectorConfig
from app.connectors.database.dialect import quote_identifier, quote_qualified_table
from app.connectors.search.types import LogQueryFilters
from app.db.models.enums import Severity

_SEVERITY_QUERY_VALUES: dict[Severity, tuple[str, ...]] = {
    Severity.INFO: ("info", "information", "debug", "trace"),
    Severity.LOW: ("low", "notice"),
    Severity.MEDIUM: ("medium", "warn", "warning"),
    Severity.HIGH: ("high", "error", "err"),
    Severity.CRITICAL: ("critical", "crit", "fatal", "emergency"),
}


def _severity_terms(severity: Severity) -> list[str]:
    return list(_SEVERITY_QUERY_VALUES.get(severity, (severity.value.lower(),)))


@dataclass(frozen=True, slots=True)
class BuiltLogQuery:
    """A validated, parameterized read-only log query."""

    statement: TextClause
    params: dict[str, Any]


def _selected_columns(config: DatabaseConnectorConfig) -> list[str]:
    columns = [
        config.timestamp_column,
        config.message_column,
        config.service_column,
        config.severity_column,
    ]
    for optional in (
        config.environment_column,
        config.host_column,
        config.request_id_column,
        config.trace_id_column,
        config.id_column,
    ):
        if optional is not None and optional not in columns:
            columns.append(optional)
    return columns


def build_log_select_query(
    filters: LogQueryFilters,
    config: DatabaseConnectorConfig,
) -> BuiltLogQuery:
    """Build a parameterized SELECT for a time-bounded log search."""

    dialect = config.dialect
    quoted_table = quote_qualified_table(config.table, dialect)
    selected = ", ".join(
        quote_identifier(column, dialect) for column in _selected_columns(config)
    )
    timestamp_col = quote_identifier(config.timestamp_column, dialect)

    where_clauses = [
        f"{timestamp_col} >= :start",
        f"{timestamp_col} <= :end",
    ]
    params: dict[str, Any] = {
        "start": filters.start.astimezone(UTC),
        "end": filters.end.astimezone(UTC),
        "limit": filters.size,
    }

    if filters.service is not None:
        service_col = quote_identifier(config.service_column, dialect)
        where_clauses.append(f"{service_col} = :service")
        params["service"] = filters.service

    if filters.environment is not None and config.environment_column is not None:
        environment_col = quote_identifier(config.environment_column, dialect)
        where_clauses.append(f"{environment_col} = :environment")
        params["environment"] = filters.environment

    if filters.severity is not None:
        severity_col = quote_identifier(config.severity_column, dialect)
        terms = _severity_terms(filters.severity)
        placeholders = ", ".join(f":severity_{index}" for index in range(len(terms)))
        where_clauses.append(f"LOWER({severity_col}) IN ({placeholders})")
        for index, term in enumerate(terms):
            params[f"severity_{index}"] = term

    where_sql = " AND ".join(where_clauses)
    sql = (
        f"SELECT {selected} "
        f"FROM {quoted_table} "
        f"WHERE {where_sql} "
        f"ORDER BY {timestamp_col} ASC "
        f"LIMIT :limit"
    )
    return BuiltLogQuery(statement=text(sql), params=params)


def health_check_query() -> BuiltLogQuery:
    """Return a minimal read-only probe query."""

    return BuiltLogQuery(statement=text("SELECT 1"), params={})
