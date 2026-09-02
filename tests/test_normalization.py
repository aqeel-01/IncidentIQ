"""Tests for log normalization."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.db.models.enums import Severity
from app.domain.events import LogEvent
from app.domain.normalization import (
    normalize_log_event,
    normalize_parsed_record,
    normalize_parsed_records,
)
from app.domain.normalization.fields import (
    normalize_service_name,
    normalize_timestamp_value,
    normalize_whitespace,
)
from app.domain.normalization.message import (
    messages_share_pattern,
    normalize_message_pattern,
)
from app.domain.parsing.types import LogFormat, ParsedLogRecord


def _record(**overrides) -> ParsedLogRecord:
    base = {
        "line_number": 1,
        "format": LogFormat.JSONL,
        "timestamp": datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        "severity": Severity.HIGH,
        "message": "hello",
        "service": "Payments-API",
        "host": " Node-1 ",
        "request_id": " req-1 ",
        "trace_id": "trace-abc",
        "raw_data": {"line": "original", "nested": {"value": 1}},
    }
    base.update(overrides)
    return ParsedLogRecord(**base)


def test_normalize_whitespace_collapses_and_trims() -> None:
    assert normalize_whitespace("  hello   world  ") == "hello world"
    assert normalize_whitespace("   ") is None


def test_normalize_service_name_lowercases() -> None:
    assert normalize_service_name(" Payments-API ") == "payments-api"


def test_normalize_timestamp_to_utc() -> None:
    plus_five = timezone(timedelta(hours=5))
    ts = datetime(2026, 9, 1, 17, 0, tzinfo=plus_five)
    normalized = normalize_timestamp_value(ts)
    assert normalized == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("User 123 failed payment", "User {id} failed payment"),
        ("User 456 failed payment", "User {id} failed payment"),
        (
            "contact 192.168.0.10 failed",
            "contact {ip} failed",
        ),
        (
            "id 550e8400-e29b-41d4-a716-446655440000 missing",
            "id {uuid} missing",
        ),
        (
            "at 2026-09-01T12:00:00Z timeout",
            "at {timestamp} timeout",
        ),
        (
            "digest deadbeefdeadbeefdeadbeefdeadbeef",
            "digest {hash}",
        ),
        (
            "request_id=req-abc123xyz timeout",
            "{request_id} timeout",
        ),
    ],
)
def test_normalize_message_pattern_replaces_dynamic_values(
    message: str, expected: str
) -> None:
    assert normalize_message_pattern(message) == expected


def test_messages_share_pattern_for_numeric_user_ids() -> None:
    assert messages_share_pattern("User 123 failed payment", "User 456 failed payment")


def test_normalize_parsed_record_preserves_raw_data() -> None:
    record = _record()
    raw_snapshot = deepcopy(record.raw_data)

    normalized = normalize_parsed_record(record)

    assert normalized.raw_data == raw_snapshot
    assert record.raw_data == raw_snapshot
    normalized.raw_data["mutated"] = True
    assert "mutated" not in record.raw_data


def test_normalize_parsed_record_normalizes_structured_fields() -> None:
    record = _record(
        message="  User   999   failed payment  ",
        severity=Severity.MEDIUM,
        raw_data={"line": "original", "environment": " Production "},
    )
    normalized = normalize_parsed_record(record)

    assert normalized.message == "User 999 failed payment"
    assert normalized.normalized_message == "User {id} failed payment"
    assert normalized.service == "payments-api"
    assert normalized.host == "node-1"
    assert normalized.request_id == "req-1"
    assert normalized.trace_id == "trace-abc"
    assert normalized.environment == "production"
    assert normalized.severity is Severity.MEDIUM
    assert normalized.timestamp is not None
    assert (
        normalized.normalized_data["normalized_message"] == "User {id} failed payment"
    )


def test_normalize_parsed_records_batch() -> None:
    records = [
        _record(message="User 1 failed"),
        _record(line_number=2, message="User 2 failed"),
    ]
    normalized = normalize_parsed_records(records)
    assert len(normalized) == 2
    assert normalized[0].normalized_message == "User {id} failed"
    assert normalized[1].normalized_message == "User {id} failed"


def test_normalize_log_event_preserves_raw_data_and_sets_normalized_data() -> None:
    event = LogEvent(
        timestamp=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        source="uploaded:app.log",
        source_type="file",
        message="User 42 failed payment",
        service=" API ",
        environment=" PROD ",
        raw_data={"original": True},
        severity=Severity.HIGH,
        host=" Host-1 ",
        request_id="req-xyz",
        trace_id="trace-1",
    )
    raw_snapshot = deepcopy(event.raw_data)

    normalized = normalize_log_event(event)

    assert normalized.raw_data == raw_snapshot
    assert normalized.message == "User 42 failed payment"
    assert normalized.normalized_data is not None
    assert (
        normalized.normalized_data["normalized_message"] == "User {id} failed payment"
    )
    assert normalized.service == "api"
    assert normalized.environment == "prod"
    assert normalized.host == "host-1"
    assert normalized.request_id == "req-xyz"


def test_normalize_log_event_does_not_mutate_input() -> None:
    event = LogEvent(
        timestamp=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        source="uploaded:app.log",
        source_type="file",
        message="  hello  ",
        raw_data={"k": "v"},
    )
    before = event.model_dump()
    normalize_log_event(event)
    assert event.model_dump() == before


def test_severity_string_in_parsed_record_is_normalized() -> None:
    # Parsed records may carry enum already; ensure values pass through unchanged.
    record = _record(severity=Severity.CRITICAL)
    normalized = normalize_parsed_record(record)
    assert normalized.severity is Severity.CRITICAL


def test_empty_message_normalizes_to_none_pattern() -> None:
    record = _record(message="   ")
    normalized = normalize_parsed_record(record)
    assert normalized.message is None
    assert normalized.normalized_message is None


def test_normalize_message_ipv6_address() -> None:
    message = "peer 2001:0db8:85a3:0000:0000:8a2e:0370:7334 unreachable"
    assert normalize_message_pattern(message) == "peer {ip} unreachable"


def test_normalize_message_multiple_dynamic_values() -> None:
    message = (
        "user 42 from 10.0.0.5 failed req-abcdef123456 "
        "trace 550e8400-e29b-41d4-a716-446655440000"
    )
    pattern = normalize_message_pattern(message)
    assert pattern == "user {id} from {ip} failed {request_id} trace {uuid}"


def test_normalize_log_event_severity_and_timestamp() -> None:
    event = LogEvent(
        timestamp=datetime(2026, 9, 1, 17, 0, tzinfo=timezone(timedelta(hours=5))),
        source="uploaded:app.log",
        source_type="file",
        message="warn",
        raw_data={"original": True},
        severity=Severity.MEDIUM,
    )
    normalized = normalize_log_event(event)
    assert normalized.timestamp == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    assert normalized.severity is Severity.MEDIUM


def test_normalized_records_from_different_messages_share_pattern() -> None:
    first = normalize_parsed_record(_record(message="User 111 failed payment"))
    second = normalize_parsed_record(
        _record(line_number=2, message="User 222 failed payment")
    )
    assert first.normalized_message == second.normalized_message
    assert first.message != second.message
