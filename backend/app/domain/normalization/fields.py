"""Normalization helpers for structured log fields."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.db.models.enums import Severity
from app.domain.parsing.fields import parse_severity, parse_timestamp

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", value.strip())
    return cleaned or None


def normalize_service_name(value: str | None) -> str | None:
    cleaned = normalize_whitespace(value)
    if cleaned is None:
        return None
    return cleaned.lower()


def normalize_host_name(value: str | None) -> str | None:
    cleaned = normalize_whitespace(value)
    if cleaned is None:
        return None
    return cleaned.lower()


def normalize_environment(value: str | None) -> str | None:
    cleaned = normalize_whitespace(value)
    if cleaned is None:
        return None
    return cleaned.lower()


def normalize_timestamp_value(value: datetime | Any | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return parse_timestamp(value)
    return parse_timestamp(value)


def normalize_severity_value(value: Severity | Any | None) -> Severity | None:
    if value is None:
        return None
    if isinstance(value, Severity):
        return value
    return parse_severity(value)


def normalize_identifier(value: str | None) -> str | None:
    """Normalize request/trace identifiers (trim only; keep original token)."""

    return normalize_whitespace(value)
