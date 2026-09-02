"""Converters between investigation pipeline artifacts."""

from __future__ import annotations

from app.domain.events import LogEvent
from app.domain.normalization.types import NormalizedLogRecord


def normalized_log_record_to_event(
    record: NormalizedLogRecord,
    *,
    source: str,
    source_type: str = "investigation",
) -> LogEvent:
    """Convert a normalized log record into a canonical log event."""

    return LogEvent(
        timestamp=record.timestamp,
        message=record.message,
        severity=record.severity,
        service=record.service,
        environment=record.environment,
        host=record.host,
        request_id=record.request_id,
        trace_id=record.trace_id,
        source=source,
        source_type=source_type,
        raw_data=dict(record.raw_data),
        normalized_data=(
            dict(record.normalized_data) if record.normalized_data else None
        ),
    )
