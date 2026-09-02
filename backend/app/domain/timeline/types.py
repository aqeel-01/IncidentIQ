"""Timeline domain types."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import Severity


class TimelineCategory(enum.StrEnum):
    """Categories displayed on an incident timeline."""

    ALERT = "alert"
    LOG = "log"
    ERROR = "error"
    METRIC = "metric"
    DEPLOYMENT = "deployment"
    TRACE = "trace"


class TimelineEntry(BaseModel):
    """A single chronological item on the incident timeline."""

    model_config = ConfigDict(frozen=True)

    id: str
    category: TimelineCategory
    timestamp: datetime
    title: str
    summary: str | None = None
    severity: Severity | None = None
    event_id: int | None = None
    error_group_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineMarkers(BaseModel):
    """Key points identified on the incident timeline."""

    model_config = ConfigDict(frozen=True)

    first_anomaly: TimelineEntry | None = None
    first_relevant_error: TimelineEntry | None = None
    first_alert: TimelineEntry | None = None
    recent_deployment: TimelineEntry | None = None
    recovery: TimelineEntry | None = None


class TimelineResult(BaseModel):
    """Full timeline for an incident."""

    model_config = ConfigDict(frozen=True)

    incident_id: int
    project_id: int
    started_at: datetime
    ended_at: datetime | None
    window_start: datetime
    window_end: datetime
    entries: list[TimelineEntry]
    markers: TimelineMarkers
    counts: dict[str, int]
