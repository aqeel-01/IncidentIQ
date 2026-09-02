"""Credential redaction helpers for Groq provider errors."""

from __future__ import annotations

import re

_GROQ_KEY_PATTERN = re.compile(r"gsk_[A-Za-z0-9]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


def sanitize_error_message(message: str, *, secrets: tuple[str, ...] = ()) -> str:
    """Redact credential-like values from provider error messages."""

    sanitized = _GROQ_KEY_PATTERN.sub("***", message)
    sanitized = _BEARER_PATTERN.sub("Bearer ***", sanitized)
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "***")
    return sanitized
