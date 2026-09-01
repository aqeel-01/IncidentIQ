"""Unit tests for event ingestion mapping and validation (no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.db.models.enums import EventType, Severity
from app.domain.events import LogEvent, MetricEvent, parse_event
from app.domain.ingestion import (
    _build_normalized_data,
    _extract_message,
    _extract_severity,
    canonical_to_event_row,
)


def _base_fields(**overrides) -> dict:
    fields = {
        "timestamp": datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        "source": "test",
        "source_type": "unit",
        "source_id": "1",
        "service": "api",
        "environment": "staging",
        "raw_data": {"line": "original payload", "nested": {"a": 1}},
    }
    fields.update(overrides)
    return fields


def test_canonical_to_row_preserves_raw_data_verbatim() -> None:
    raw = {"line": "original payload", "nested": {"a": 1}}
    event = LogEvent(**_base_fields(raw_data=raw), message="err")
    row = canonical_to_event_row(event, project_id=1, service_id=2)

    assert row.raw_data == raw
    assert row.raw_data is not event.raw_data  # defensive copy
    assert row.project_id == 1
    assert row.service_id == 2
    assert row.event_type is EventType.LOG
    assert row.message == "err"
    assert row.severity is None


def test_timestamp_stored_as_utc() -> None:
    plus_five = timezone(timedelta(hours=5))
    event = LogEvent(
        **_base_fields(timestamp=datetime(2026, 9, 1, 17, 0, tzinfo=plus_five)),
        message="x",
    )
    row = canonical_to_event_row(event, project_id=1, service_id=None)
    assert row.timestamp == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    assert row.timestamp.tzinfo is UTC


def test_extract_message_and_severity_by_type() -> None:
    log = LogEvent(**_base_fields(), message="boom", severity=Severity.HIGH)
    metric = MetricEvent(**_base_fields(), metric_name="cpu", value=0.9)
    assert _extract_message(log) == "boom"
    assert _extract_severity(log) is Severity.HIGH
    assert _extract_message(metric) == "cpu=0.9"
    assert _extract_severity(metric) is None


def test_build_normalized_data_merges_type_specific_fields() -> None:
    event = LogEvent(
        **_base_fields(normalized_data={"custom": True}),
        message="x",
        host="h1",
        severity=Severity.LOW,
    )
    normalized = _build_normalized_data(event)
    assert normalized is not None
    assert normalized["custom"] is True
    assert normalized["message"] == "x"
    assert normalized["host"] == "h1"
    assert normalized["severity"] == "LOW"
    assert "raw_data" not in normalized


def test_parse_event_rejects_invalid_dict() -> None:
    with pytest.raises(ValidationError):
        parse_event({**_base_fields(), "event_type": "LOG"})  # missing message
