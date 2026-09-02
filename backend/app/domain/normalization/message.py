"""Message normalization and dynamic-value placeholder replacement."""

from __future__ import annotations

import re

from app.domain.normalization.fields import normalize_whitespace

# Replacement order matters: specific patterns before broad numeric IDs.
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_IPV6_RE = re.compile(r"\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{0,4}\b", re.IGNORECASE)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3})\b"
)
_ISO_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
_HASH_RE = re.compile(r"\b[a-f0-9]{32,64}\b", re.IGNORECASE)
_REQUEST_ID_RE = re.compile(
    r"\b(?:(?:req(?:uest)?[_-]?id[=:]?\s*)[A-Za-z0-9_-]{6,}|req-[A-Za-z0-9_-]{6,})\b",
    re.IGNORECASE,
)
_NUMERIC_ID_RE = re.compile(r"\b\d+\b")

_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_UUID_RE, "{uuid}"),
    (_IPV6_RE, "{ip}"),
    (_IPV4_RE, "{ip}"),
    (_ISO_TS_RE, "{timestamp}"),
    (_HASH_RE, "{hash}"),
    (_REQUEST_ID_RE, "{request_id}"),
    (_NUMERIC_ID_RE, "{id}"),
)


def normalize_message_pattern(message: str | None) -> str | None:
    """Return a fingerprint-friendly message with dynamic values replaced."""

    cleaned = normalize_whitespace(message)
    if cleaned is None:
        return None

    normalized = cleaned
    for pattern, placeholder in _REPLACEMENTS:
        normalized = pattern.sub(placeholder, normalized)

    # Collapse repeated placeholders and tidy spacing.
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def messages_share_pattern(left: str | None, right: str | None) -> bool:
    """Return whether two messages normalize to the same logical pattern."""

    return normalize_message_pattern(left) == normalize_message_pattern(right)
