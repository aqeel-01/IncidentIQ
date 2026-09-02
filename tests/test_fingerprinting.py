"""Tests for deterministic event fingerprinting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models.enums import EventType, Severity
from app.domain.events import LogEvent, MetricEvent
from app.domain.fingerprinting import (
    build_fingerprint_material,
    compute_event_fingerprint,
    fingerprint_canonical_event,
    fingerprint_log_event,
    fingerprint_normalized_log_record,
)
from app.domain.normalization import normalize_log_event, normalize_parsed_record
from app.domain.parsing.types import LogFormat, ParsedLogRecord


def _log_event(message: str, **overrides) -> LogEvent:
    base = {
        "timestamp": datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        "source": "uploaded:app.log",
        "source_type": "file",
        "message": message,
        "service": "payments-api",
        "severity": Severity.HIGH,
        "raw_data": {"line": message},
    }
    base.update(overrides)
    return LogEvent(**base)


def test_fingerprint_is_deterministic() -> None:
    kwargs = {
        "event_type": EventType.LOG,
        "source": "uploaded:app.log",
        "service": "payments-api",
        "severity": Severity.HIGH,
        "normalized_message": "User {id} failed payment",
    }
    first = compute_event_fingerprint(**kwargs)
    second = compute_event_fingerprint(**kwargs)
    assert first == second
    assert len(first) == 64


def test_same_logical_messages_produce_same_fingerprint() -> None:
    base = {
        "event_type": EventType.LOG,
        "source": "uploaded:app.log",
        "service": "payments-api",
        "severity": Severity.HIGH,
    }
    fp_one = compute_event_fingerprint(
        **base, normalized_message="User {id} failed payment"
    )
    fp_two = compute_event_fingerprint(
        **base, normalized_message="User {id} failed payment"
    )
    assert fp_one == fp_two

    event_a = fingerprint_log_event(
        normalize_log_event(_log_event("User 123 failed payment"))
    )
    event_b = fingerprint_log_event(
        normalize_log_event(_log_event("User 456 failed payment"))
    )
    assert event_a == event_b


def test_different_logical_messages_produce_distinct_fingerprints() -> None:
    base = {
        "event_type": EventType.LOG,
        "source": "uploaded:app.log",
        "service": "payments-api",
        "severity": Severity.HIGH,
    }
    payment = compute_event_fingerprint(
        **base, normalized_message="User {id} failed payment"
    )
    timeout = compute_event_fingerprint(
        **base, normalized_message="connection {id} timed out"
    )
    assert payment != timeout


@pytest.mark.parametrize(
    ("field", "value_a", "value_b"),
    [
        ("source", "uploaded:a.log", "uploaded:b.log"),
        ("service", "payments-api", "billing-api"),
        ("severity", Severity.HIGH, Severity.LOW),
        ("event_type", EventType.LOG, EventType.ALERT),
    ],
)
def test_property_changes_produce_distinct_fingerprints(
    field: str, value_a, value_b
) -> None:
    common = {
        "event_type": EventType.LOG,
        "source": "uploaded:app.log",
        "service": "payments-api",
        "severity": Severity.HIGH,
        "normalized_message": "User {id} failed payment",
    }
    left = dict(common)
    right = dict(common)
    left[field] = value_a
    right[field] = value_b
    assert compute_event_fingerprint(**left) != compute_event_fingerprint(**right)


def test_service_name_is_normalized_before_hashing() -> None:
    fp_lower = compute_event_fingerprint(
        event_type=EventType.LOG,
        source="uploaded:app.log",
        service="payments-api",
        severity=Severity.HIGH,
        normalized_message="error",
    )
    fp_mixed = compute_event_fingerprint(
        event_type=EventType.LOG,
        source="uploaded:app.log",
        service=" Payments-API ",
        severity=Severity.HIGH,
        normalized_message="error",
    )
    assert fp_lower == fp_mixed


def test_build_fingerprint_material_is_stable_and_ordered() -> None:
    material = build_fingerprint_material(
        event_type=EventType.LOG,
        source="uploaded:app.log",
        service="api",
        severity=Severity.MEDIUM,
        normalized_message="timeout",
    )
    assert list(material.keys()) == [
        "event_type",
        "source",
        "service",
        "severity",
        "normalized_message",
    ]
    assert material["event_type"] == "LOG"
    assert material["severity"] == "MEDIUM"


def test_fingerprint_normalized_log_record() -> None:
    parsed = ParsedLogRecord(
        line_number=1,
        format=LogFormat.JSONL,
        severity=Severity.HIGH,
        message="User 999 failed payment",
        normalized_message="User {id} failed payment",
        service="payments-api",
        raw_data={"k": "v"},
    )
    normalized = normalize_parsed_record(parsed)
    fp = fingerprint_normalized_log_record(
        normalized, source="uploaded:app.log", event_type=EventType.LOG
    )
    expected = compute_event_fingerprint(
        event_type=EventType.LOG,
        source="uploaded:app.log",
        service="payments-api",
        severity=Severity.HIGH,
        normalized_message="User {id} failed payment",
    )
    assert fp == expected


def test_fingerprint_canonical_event_supports_log_events() -> None:
    event = normalize_log_event(_log_event("User 1 failed payment"))
    assert fingerprint_canonical_event(event) == fingerprint_log_event(event)


def test_fingerprint_canonical_event_rejects_unsupported_types() -> None:
    metric = MetricEvent(
        timestamp=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        source="prometheus",
        source_type="metrics",
        metric_name="latency",
        value=1.0,
        raw_data={},
    )
    with pytest.raises(TypeError):
        fingerprint_canonical_event(metric)
