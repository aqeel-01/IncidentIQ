"""Canonical event domain schemas (see SRS §4).

These Pydantic models are the internal, source-agnostic representation of every
event flowing through the investigation pipeline. Connectors are responsible for
converting raw source payloads into these models; nothing here may depend on a
specific connector, transport, or the database layer.

All events share a common envelope (:class:`CanonicalEventBase`) and are tagged
with an ``event_type`` discriminator so a heterogeneous stream can be
(de)serialized via :data:`AnyCanonicalEvent` / :func:`parse_event`.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

# Reuse the shared enums rather than duplicating them (see engineering standards
# §16/§17). They are plain enums with no database coupling.
from app.db.models.enums import EventType, Severity


class AlertStatus(enum.StrEnum):
    FIRING = "FIRING"
    RESOLVED = "RESOLVED"


class CanonicalEventBase(BaseModel):
    """Common envelope shared by every canonical event.

    ``raw_data`` preserves the original source payload for traceability;
    ``normalized_data`` optionally holds derived/cleaned fields.
    """

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    source: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str | None = None
    service: str | None = None
    environment: str | None = None
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any] | None = None

    @field_validator("timestamp")
    @classmethod
    def _normalize_to_utc(cls, value: datetime) -> datetime:
        """Normalize all timestamps to timezone-aware UTC (SRS §8).

        Naive datetimes are assumed to already be UTC.
        """

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class LogEvent(CanonicalEventBase):
    event_type: Literal[EventType.LOG] = EventType.LOG

    message: str
    severity: Severity | None = None
    host: str | None = None
    request_id: str | None = None
    trace_id: str | None = None


class MetricEvent(CanonicalEventBase):
    event_type: Literal[EventType.METRIC] = EventType.METRIC

    metric_name: str = Field(min_length=1)
    value: float
    unit: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class AlertEvent(CanonicalEventBase):
    event_type: Literal[EventType.ALERT] = EventType.ALERT

    name: str = Field(min_length=1)
    status: AlertStatus = AlertStatus.FIRING
    severity: Severity | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class DeploymentEvent(CanonicalEventBase):
    event_type: Literal[EventType.DEPLOYMENT] = EventType.DEPLOYMENT

    version: str | None = None
    commit_sha: str | None = None
    author: str | None = None
    repository: str | None = None
    changed_files: list[str] = Field(default_factory=list)


class TraceEvent(CanonicalEventBase):
    event_type: Literal[EventType.TRACE] = EventType.TRACE

    trace_id: str = Field(min_length=1)
    span_id: str = Field(min_length=1)
    parent_span_id: str | None = None
    operation_name: str | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    status: str | None = None


# Discriminated union enabling type-safe (de)serialization of a mixed stream.
AnyCanonicalEvent = Annotated[
    LogEvent | MetricEvent | AlertEvent | DeploymentEvent | TraceEvent,
    Field(discriminator="event_type"),
]

_event_adapter: TypeAdapter[Any] = TypeAdapter(AnyCanonicalEvent)


def parse_event(data: dict[str, Any]) -> CanonicalEventBase:
    """Deserialize a mapping into the correct canonical event subclass."""

    return _event_adapter.validate_python(data)


def parse_event_json(data: str | bytes) -> CanonicalEventBase:
    """Deserialize a JSON document into the correct canonical event subclass."""

    return _event_adapter.validate_json(data)
