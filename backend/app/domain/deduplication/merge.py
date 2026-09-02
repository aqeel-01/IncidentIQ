"""Pure merge helpers for error-group timestamp and occurrence tracking."""

from __future__ import annotations

from datetime import UTC, datetime


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def merge_error_group_timestamps(
    *,
    occurrence_count: int,
    first_seen: datetime,
    last_seen: datetime,
    event_timestamp: datetime,
) -> tuple[int, datetime, datetime]:
    """Return updated ``(occurrence_count, first_seen, last_seen)`` after merge."""

    first_seen_utc = _to_utc(first_seen)
    last_seen_utc = _to_utc(last_seen)
    event_timestamp_utc = _to_utc(event_timestamp)

    return (
        occurrence_count + 1,
        event_timestamp_utc
        if event_timestamp_utc < first_seen_utc
        else first_seen_utc,
        event_timestamp_utc
        if event_timestamp_utc > last_seen_utc
        else last_seen_utc,
    )
