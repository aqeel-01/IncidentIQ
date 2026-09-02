"""Convert SQL rows into canonical log events."""

from __future__ import annotations

from typing import Any

from app.connectors.database.config import DatabaseConnectorConfig
from app.domain.events import LogEvent
from app.domain.parsing.fields import parse_severity, parse_timestamp


def _column_value(row: dict[str, Any], column: str | None) -> Any | None:
    if column is None:
        return None
    if column in row and row[column] not in (None, ""):
        return row[column]
    return None


def sql_row_to_log_event(
    row: dict[str, Any],
    *,
    config: DatabaseConnectorConfig,
    source_name: str,
) -> LogEvent | None:
    """Map a single SQL row to a :class:`LogEvent`."""

    message_value = _column_value(row, config.message_column)
    if message_value is None:
        return None
    message = str(message_value).strip()
    if not message:
        return None

    timestamp = parse_timestamp(_column_value(row, config.timestamp_column))
    if timestamp is None:
        return None

    service_value = (
        _column_value(row, config.service_column) or config.default_service
    )
    environment_value = (
        _column_value(row, config.environment_column) or config.default_environment
    )
    severity = parse_severity(_column_value(row, config.severity_column))
    host_value = _column_value(row, config.host_column)
    request_id_value = _column_value(row, config.request_id_column)
    trace_id_value = _column_value(row, config.trace_id_column)
    source_id_value = _column_value(row, config.id_column)

    return LogEvent(
        timestamp=timestamp,
        source=source_name,
        source_type="database",
        source_id=str(source_id_value) if source_id_value is not None else None,
        service=str(service_value) if service_value is not None else None,
        environment=str(environment_value) if environment_value is not None else None,
        message=message,
        severity=severity,
        host=str(host_value) if host_value is not None else None,
        request_id=str(request_id_value) if request_id_value is not None else None,
        trace_id=str(trace_id_value) if trace_id_value is not None else None,
        raw_data=dict(row),
    )


def sql_rows_to_log_events(
    rows: list[dict[str, Any]],
    *,
    config: DatabaseConnectorConfig,
    source_name: str,
) -> list[LogEvent]:
    """Convert SQL rows into canonical log events."""

    events: list[LogEvent] = []
    for row in rows:
        event = sql_row_to_log_event(row, config=config, source_name=source_name)
        if event is not None:
            events.append(event)
    return events
