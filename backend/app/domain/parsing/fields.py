"""Automatic extraction of common log fields from arbitrary key/value data."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.db.models.enums import Severity
from app.domain.parsing.mapping import ManualFieldMapping, extract_manual_fields
from app.domain.parsing.types import LogFormat, ParsedLogRecord

# Aliases for automatic field mapping (SRS §5).
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "ts", "@timestamp", "datetime", "date"),
    "severity": ("severity", "level", "log_level", "loglevel", "lvl"),
    "message": ("message", "msg", "log", "text", "body", "error"),
    "service": ("service", "service_name", "app", "application", "component"),
    "host": ("host", "hostname", "node", "server"),
    "request_id": (
        "request_id",
        "requestid",
        "req_id",
        "correlation_id",
        "correlationid",
        "x_request_id",
    ),
    "trace_id": ("trace_id", "traceid", "trace", "span_trace_id"),
}

_SEVERITY_MAP: dict[str, Severity] = {
    "trace": Severity.INFO,
    "debug": Severity.INFO,
    "info": Severity.INFO,
    "information": Severity.INFO,
    "low": Severity.LOW,
    "notice": Severity.LOW,
    "warn": Severity.MEDIUM,
    "warning": Severity.MEDIUM,
    "error": Severity.HIGH,
    "err": Severity.HIGH,
    "critical": Severity.CRITICAL,
    "crit": Severity.CRITICAL,
    "fatal": Severity.CRITICAL,
    "emergency": Severity.CRITICAL,
}

_ISO_PREFIX = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)
_BRACKET_LEVEL = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b",
    re.IGNORECASE,
)
_KV_PATTERN = re.compile(r"(\w+)=('[^']*'|\"[^\"]*\"|\S+)")


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _lookup(data: dict[str, Any], aliases: tuple[str, ...]) -> Any | None:
    normalized = {_normalize_key(k): v for k, v in data.items()}
    for alias in aliases:
        if alias in normalized and normalized[alias] not in (None, ""):
            return normalized[alias]
    return None


def parse_timestamp(value: Any) -> datetime | None:
    """Best-effort timestamp parsing into UTC."""

    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        # Assume epoch seconds (or ms if very large).
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=UTC)

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S,%f",
            "%Y/%m/%d %H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_severity(value: Any) -> Severity | None:
    if value is None:
        return None
    if isinstance(value, Severity):
        return value
    token = str(value).strip().lower()
    return _SEVERITY_MAP.get(token)


def extract_common_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Return normalized common fields found in ``data``."""

    result: dict[str, Any] = {}
    for field, aliases in _FIELD_ALIASES.items():
        raw = _lookup(data, aliases)
        if raw is None:
            continue
        if field == "timestamp":
            result[field] = parse_timestamp(raw)
        elif field == "severity":
            result[field] = parse_severity(raw)
        else:
            result[field] = str(raw)
    return result


def extract_from_plain_line(line: str) -> dict[str, Any]:
    """Heuristically pull fields from an unstructured text line."""

    data: dict[str, Any] = {"message": line.strip()}
    match = _ISO_PREFIX.match(line)
    if match:
        data["timestamp"] = match.group(1)
        remainder = line[match.end() :].strip()
        level_match = _BRACKET_LEVEL.search(remainder)
        if level_match:
            data["severity"] = level_match.group(1)
            remainder = (
                remainder[: level_match.start()] + remainder[level_match.end() :]
            ).strip()
        data["message"] = remainder or line.strip()
    else:
        level_match = _BRACKET_LEVEL.search(line)
        if level_match:
            data["severity"] = level_match.group(1)
    return data


def extract_from_structured_line(line: str) -> dict[str, Any]:
    """Parse key=value / key='value' structured text lines."""

    data: dict[str, Any] = {}
    for key, raw_value in _KV_PATTERN.findall(line):
        value = raw_value.strip("'\"")
        data[_normalize_key(key)] = value
    if "message" not in data and "msg" not in data:
        # Residual text after last key=value pair becomes the message.
        tail = _KV_PATTERN.sub("", line).strip()
        if tail:
            data["message"] = tail
    return data


def build_record(
    *,
    line_number: int,
    fmt: LogFormat,
    data: dict[str, Any],
    raw_data: dict[str, Any] | None = None,
    field_mapping: ManualFieldMapping | None = None,
) -> ParsedLogRecord:
    if field_mapping is None or field_mapping.is_empty():
        fields = extract_common_fields(data)
    else:
        auto_fields = extract_common_fields(data)
        manual_fields = extract_manual_fields(data, field_mapping)
        mapped_keys = set(field_mapping.defined_mappings())
        fields = {
            **{k: v for k, v in auto_fields.items() if k not in mapped_keys},
            **manual_fields,
        }

    source_raw = raw_data if raw_data is not None else dict(data)
    return ParsedLogRecord(
        line_number=line_number,
        format=fmt,
        timestamp=fields.get("timestamp"),
        severity=fields.get("severity"),
        message=fields.get("message"),
        service=fields.get("service"),
        host=fields.get("host"),
        request_id=fields.get("request_id"),
        trace_id=fields.get("trace_id"),
        raw_data=source_raw,
    )
