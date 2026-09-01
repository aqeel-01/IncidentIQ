"""Tests for canonical event domain schemas (serialization/validation)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.db.models.enums import EventType, Severity
from app.domain.events import (
    AlertEvent,
    AlertStatus,
    CanonicalEventBase,
    DeploymentEvent,
    LogEvent,
    MetricEvent,
    TraceEvent,
    parse_event,
    parse_event_json,
)

TS = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

BASE_FIELDS = {
    "timestamp": TS,
    "source": "uploaded:app.log",
    "source_type": "file",
    "source_id": "line-42",
    "service": "payments-api",
    "environment": "production",
    "raw_data": {"original": "..."},
}


def _samples() -> list[CanonicalEventBase]:
    return [
        LogEvent(**BASE_FIELDS, message="boom", severity=Severity.HIGH, host="h1"),
        MetricEvent(**BASE_FIELDS, metric_name="latency_ms", value=512.0, unit="ms"),
        AlertEvent(**BASE_FIELDS, name="HighErrorRate", status=AlertStatus.FIRING),
        DeploymentEvent(**BASE_FIELDS, version="v1.2.3", changed_files=["a.py"]),
        TraceEvent(**BASE_FIELDS, trace_id="t1", span_id="s1", duration_ms=12.5),
    ]


@pytest.mark.parametrize("event", _samples(), ids=lambda e: e.event_type.value)
def test_python_roundtrip_preserves_type_and_data(event: CanonicalEventBase) -> None:
    restored = parse_event(event.model_dump())
    assert type(restored) is type(event)
    assert restored == event


@pytest.mark.parametrize("event", _samples(), ids=lambda e: e.event_type.value)
def test_json_roundtrip_preserves_type_and_data(event: CanonicalEventBase) -> None:
    restored = parse_event_json(event.model_dump_json())
    assert type(restored) is type(event)
    assert restored == event


def test_discriminator_selects_correct_subclass() -> None:
    data = {**BASE_FIELDS, "event_type": "METRIC", "metric_name": "cpu", "value": 0.9}
    restored = parse_event(data)
    assert isinstance(restored, MetricEvent)
    assert restored.metric_name == "cpu"


def test_naive_timestamp_assumed_utc() -> None:
    event = LogEvent(
        **{**BASE_FIELDS, "timestamp": datetime(2026, 9, 1, 12, 0)},
        message="x",
    )
    assert event.timestamp.tzinfo is UTC
    assert event.timestamp == TS


def test_aware_timestamp_converted_to_utc() -> None:
    plus_five = timezone(timedelta(hours=5))
    event = LogEvent(
        **{**BASE_FIELDS, "timestamp": datetime(2026, 9, 1, 17, 0, tzinfo=plus_five)},
        message="x",
    )
    assert event.timestamp == TS
    assert event.timestamp.utcoffset() == timedelta(0)


def test_json_serialization_uses_string_event_type() -> None:
    event = _samples()[0]
    dumped = event.model_dump_json()
    assert '"event_type":"LOG"' in dumped


def test_missing_required_subclass_field_raises() -> None:
    with pytest.raises(ValidationError):
        LogEvent(**BASE_FIELDS)  # missing 'message'


def test_missing_required_base_field_raises() -> None:
    fields = {k: v for k, v in BASE_FIELDS.items() if k != "raw_data"}
    with pytest.raises(ValidationError):
        LogEvent(**fields, message="x")


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        LogEvent(**BASE_FIELDS, message="x", unexpected="nope")


def test_blank_source_rejected() -> None:
    with pytest.raises(ValidationError):
        LogEvent(**{**BASE_FIELDS, "source": ""}, message="x")


def test_unknown_event_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_event({**BASE_FIELDS, "event_type": "SMOKE_SIGNAL"})


def test_negative_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        TraceEvent(**BASE_FIELDS, trace_id="t", span_id="s", duration_ms=-1.0)


def test_defaults_applied() -> None:
    event = AlertEvent(**BASE_FIELDS, name="A")
    assert event.status is AlertStatus.FIRING
    assert event.labels == {}
    assert event.normalized_data is None
    assert event.event_type is EventType.ALERT
