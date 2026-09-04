"""Log normalization service for parsed records and canonical log events."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from app.domain.events import LogEvent
from app.domain.normalization.fields import (
    normalize_environment,
    normalize_host_name,
    normalize_identifier,
    normalize_service_name,
    normalize_severity_value,
    normalize_timestamp_value,
    normalize_whitespace,
)
from app.domain.normalization.message import normalize_message_pattern
from app.domain.normalization.types import NormalizedLogRecord
from app.domain.parsing.types import ParsedLogRecord


def normalize_parsed_record(
    record: ParsedLogRecord,
    *,
    copy_raw_data: bool = True,
) -> NormalizedLogRecord:
    """Normalize a parsed log record while preserving ``raw_data`` verbatim.

    Set ``copy_raw_data=False`` on streaming hot paths to avoid duplicating the
    raw payload when the caller will not mutate it.
    """

    message = normalize_whitespace(record.message)
    normalized_message = normalize_message_pattern(message)

    normalized_data: dict[str, Any] = {
        "normalized_message": normalized_message,
        "host": normalize_host_name(record.host),
        "request_id": normalize_identifier(record.request_id),
        "trace_id": normalize_identifier(record.trace_id),
        "environment": normalize_environment(
            record.raw_data.get("environment")
            if isinstance(record.raw_data.get("environment"), str)
            else None
        ),
    }

    raw_data = dict(record.raw_data) if copy_raw_data else record.raw_data

    return NormalizedLogRecord(
        line_number=record.line_number,
        format=record.format,
        timestamp=normalize_timestamp_value(record.timestamp),
        severity=normalize_severity_value(record.severity),
        message=message,
        normalized_message=normalized_message,
        service=normalize_service_name(record.service),
        host=normalize_host_name(record.host),
        request_id=normalize_identifier(record.request_id),
        trace_id=normalize_identifier(record.trace_id),
        environment=normalized_data.get("environment"),
        normalized_data={k: v for k, v in normalized_data.items() if v is not None},
        raw_data=raw_data,
    )


def iter_normalize_parsed_records(
    records: Iterable[ParsedLogRecord],
    *,
    copy_raw_data: bool = False,
) -> Iterator[NormalizedLogRecord]:
    """Lazily normalize records without materializing an intermediate list."""

    for record in records:
        yield normalize_parsed_record(record, copy_raw_data=copy_raw_data)


def normalize_parsed_records(
    records: Iterable[ParsedLogRecord],
    *,
    copy_raw_data: bool = True,
) -> list[NormalizedLogRecord]:
    return list(
        iter_normalize_parsed_records(records, copy_raw_data=copy_raw_data)
    )


def normalize_log_event(event: LogEvent) -> LogEvent:
    """Normalize a canonical :class:`LogEvent` without mutating ``raw_data``."""

    message = normalize_whitespace(event.message)
    normalized_message = normalize_message_pattern(message)

    normalized_data = dict(event.normalized_data) if event.normalized_data else {}
    normalized_data.update(
        {
            "normalized_message": normalized_message,
            "host": normalize_host_name(event.host),
        }
    )
    normalized_data = {k: v for k, v in normalized_data.items() if v is not None}

    return event.model_copy(
        update={
            "timestamp": normalize_timestamp_value(event.timestamp),
            "severity": normalize_severity_value(event.severity),
            "message": message or event.message,
            "service": normalize_service_name(event.service),
            "host": normalize_host_name(event.host),
            "request_id": normalize_identifier(event.request_id),
            "trace_id": normalize_identifier(event.trace_id),
            "environment": normalize_environment(event.environment),
            "normalized_data": normalized_data or None,
            "raw_data": dict(event.raw_data),
        }
    )
