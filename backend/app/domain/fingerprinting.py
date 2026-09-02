"""Deterministic event fingerprinting for deduplication and error grouping."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.db.models.enums import EventType, Severity
from app.domain.events import CanonicalEventBase, LogEvent
from app.domain.normalization.fields import normalize_service_name
from app.domain.normalization.message import normalize_message_pattern
from app.domain.normalization.types import NormalizedLogRecord

# Delimiter-safe canonical JSON keeps fingerprints stable across Python versions.
_JSON_SEPARATORS = (",", ":")


def _canonical_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Severity):
        return value.value
    if isinstance(value, EventType):
        return value.value
    return str(value).strip()


def build_fingerprint_material(
    *,
    event_type: EventType | str,
    source: str,
    service: str | None,
    severity: Severity | str | None,
    normalized_message: str | None,
) -> dict[str, str]:
    """Build the ordered property bag hashed into a fingerprint."""

    return {
        "event_type": _canonical_value(event_type),
        "source": source.strip(),
        "service": _canonical_value(normalize_service_name(service)),
        "severity": _canonical_value(severity),
        "normalized_message": _canonical_value(normalized_message),
    }


def compute_event_fingerprint(
    *,
    event_type: EventType | str,
    source: str,
    service: str | None,
    severity: Severity | str | None,
    normalized_message: str | None,
) -> str:
    """Return a stable 64-character SHA-256 hex fingerprint.

    The same logical event (identical normalized properties) always produces the
    same fingerprint. Dynamic message values must already be normalized before
    calling this function.
    """

    material = build_fingerprint_material(
        event_type=event_type,
        source=source,
        service=service,
        severity=severity,
        normalized_message=normalized_message,
    )
    payload = json.dumps(
        material, sort_keys=True, separators=_JSON_SEPARATORS, ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_logical_error_fingerprint(
    *,
    event_type: EventType | str,
    service: str | None,
    severity: Severity | str | None,
    normalized_message: str | None,
) -> str:
    """Fingerprint for error-group deduplication (source-agnostic).

    Events that represent the same logical failure across different sources
    share a fingerprint when their normalized properties match.
    """

    return compute_event_fingerprint(
        event_type=event_type,
        source="",
        service=service,
        severity=severity,
        normalized_message=normalized_message,
    )


def _normalized_message_for_log_event(event: LogEvent) -> str | None:
    if event.normalized_data:
        value = event.normalized_data.get("normalized_message")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return normalize_message_pattern(event.message)


def fingerprint_log_event(event: LogEvent) -> str:
    """Fingerprint a canonical log event using normalized message properties."""

    return compute_event_fingerprint(
        event_type=event.event_type,
        source=event.source,
        service=event.service,
        severity=event.severity,
        normalized_message=_normalized_message_for_log_event(event),
    )


def fingerprint_normalized_log_record(
    record: NormalizedLogRecord,
    *,
    source: str,
    event_type: EventType = EventType.LOG,
) -> str:
    """Fingerprint a normalized parsed log record."""

    normalized_message = record.normalized_message
    if normalized_message is None and record.normalized_data:
        value = record.normalized_data.get("normalized_message")
        if isinstance(value, str):
            normalized_message = value

    return compute_event_fingerprint(
        event_type=event_type,
        source=source,
        service=record.service,
        severity=record.severity,
        normalized_message=normalized_message,
    )


def fingerprint_canonical_event(event: CanonicalEventBase) -> str:
    """Fingerprint supported canonical events (currently log events only)."""

    if isinstance(event, LogEvent):
        return fingerprint_log_event(event)
    raise TypeError(
        f"fingerprinting not supported for event type {event.event_type!r}"
    )


def fingerprint_logical_log_event(event: LogEvent) -> str:
    """Source-agnostic fingerprint for error-group merging."""

    return compute_logical_error_fingerprint(
        event_type=event.event_type,
        service=event.service,
        severity=event.severity,
        normalized_message=_normalized_message_for_log_event(event),
    )


def fingerprint_logical_normalized_log_record(
    record: NormalizedLogRecord,
    *,
    event_type: EventType = EventType.LOG,
) -> str:
    """Source-agnostic fingerprint for a normalized parsed log record."""

    normalized_message = record.normalized_message
    if normalized_message is None and record.normalized_data:
        value = record.normalized_data.get("normalized_message")
        if isinstance(value, str):
            normalized_message = value

    return compute_logical_error_fingerprint(
        event_type=event_type,
        service=record.service,
        severity=record.severity,
        normalized_message=normalized_message,
    )
