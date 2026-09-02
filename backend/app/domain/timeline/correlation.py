"""Incident correlation helpers for timeline construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db.models.incident import Incident


@dataclass(frozen=True, slots=True)
class TimelineWindow:
    """Time bounds used when collecting timeline evidence."""

    start: datetime
    end: datetime


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def incident_timeline_window(
    incident: Incident,
    *,
    deployment_lookback: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> TimelineWindow:
    """Derive the collection window for an incident."""

    started_at = _to_utc(incident.started_at)
    ended_at = _to_utc(incident.ended_at) if incident.ended_at is not None else None
    window_end = ended_at or _to_utc(now or datetime.now(UTC))
    window_start = min(started_at - deployment_lookback, started_at)
    return TimelineWindow(start=window_start, end=window_end)
