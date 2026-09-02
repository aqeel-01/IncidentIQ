"""Map persisted records to timeline entries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.models.enums import Severity
from app.db.models.error_group import ErrorGroup
from app.db.models.event import Event
from app.domain.timeline.types import TimelineCategory, TimelineEntry


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _event_category(row: Event) -> TimelineCategory:
    return TimelineCategory(row.event_type.value.lower())


def _event_title(row: Event) -> str:
    if row.message:
        return row.message
    return f"{row.event_type.value.title()} from {row.source}"


def _normalized_value(row: Event, key: str) -> Any | None:
    if not isinstance(row.normalized_data, dict):
        return None
    return row.normalized_data.get(key)


def event_to_timeline_entry(row: Event) -> TimelineEntry:
    """Convert an ``Event`` ORM row into a timeline entry."""

    metadata: dict[str, Any] = {
        "source": row.source,
        "source_type": row.source_type,
        "environment": row.environment,
    }
    if row.normalized_data:
        metadata["normalized_data"] = dict(row.normalized_data)
    if row.service_id is not None:
        metadata["service_id"] = row.service_id

    return TimelineEntry(
        id=f"event:{row.id}",
        category=_event_category(row),
        timestamp=_to_utc(row.timestamp),
        title=_event_title(row),
        summary=row.message,
        severity=row.severity,
        event_id=row.id,
        error_group_id=row.error_group_id,
        metadata=metadata,
    )


def error_group_to_timeline_entry(group: ErrorGroup) -> TimelineEntry:
    """Convert an ``ErrorGroup`` into a timeline error entry."""

    metadata: dict[str, Any] = {
        "occurrence_count": group.occurrence_count,
        "fingerprint": group.fingerprint,
        "last_seen": _to_utc(group.last_seen).isoformat(),
    }
    if group.service_id is not None:
        metadata["service_id"] = group.service_id

    return TimelineEntry(
        id=f"error_group:{group.id}",
        category=TimelineCategory.ERROR,
        timestamp=_to_utc(group.first_seen),
        title=group.normalized_message,
        summary=(
            f"seen {group.occurrence_count} times; "
            f"last at {_to_utc(group.last_seen).isoformat()}"
        ),
        severity=group.severity,
        error_group_id=group.id,
        metadata=metadata,
    )


def is_anomaly_entry(entry: TimelineEntry) -> bool:
    """Return whether an entry qualifies as an anomaly marker."""

    if entry.category is TimelineCategory.METRIC:
        return True
    if entry.severity is None:
        return False
    return entry.severity in {
        Severity.MEDIUM,
        Severity.HIGH,
        Severity.CRITICAL,
    }


def is_resolved_alert(entry: TimelineEntry) -> bool:
    """Return whether a timeline entry represents a resolved alert."""

    if entry.category is not TimelineCategory.ALERT:
        return False
    status = entry.metadata.get("normalized_data", {}).get("status")
    return str(status).upper() == "RESOLVED"
