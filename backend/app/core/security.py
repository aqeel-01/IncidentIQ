"""Central secret redaction for logs and user-facing error details."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core.config import Settings

_BEARER_PATTERN = re.compile(r"(?i)(Bearer|token)\s+\S+")
_BASIC_PATTERN = re.compile(r"(?i)(Basic)\s+\S+")
_PASSWORD_ASSIGN_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|private[_-]?key|client[_-]?secret)\s*[:=]\s*([^\s,;]+)"
)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_GROQ_KEY_PATTERN = re.compile(r"\bgsk_[A-Za-z0-9]+\b", re.IGNORECASE)
_GITHUB_TOKEN_PATTERN = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b"
)
_DSN_PASSWORD_PATTERN = re.compile(
    r"(?i)((?:postgres(?:ql)?|mysql|mariadb|redis|mongodb(?:\+srv)?|amqp|"
    r"http|https)://[^:/@\s]+:)([^@/\s]+)(@)"
)
_REDACTED = "***"


def secrets_from_settings(settings: Settings | None) -> tuple[str, ...]:
    """Collect non-empty configured secret values for explicit redaction."""

    if settings is None:
        return ()
    values = (
        settings.groq_api_key,
        settings.jwt_secret_key,
        settings.connector_secret_key,
    )
    return tuple(value for value in values if value and value.strip())


def redact_dsn(value: str) -> str:
    """Redact password components embedded in connection URLs."""

    return _DSN_PASSWORD_PATTERN.sub(rf"\1{_REDACTED}\3", value)


def sanitize_error_message(
    message: str,
    *,
    secrets: Iterable[str] = (),
) -> str:
    """Redact credential-like values from free-form error text."""

    sanitized = str(message)
    sanitized = redact_dsn(sanitized)
    sanitized = _BEARER_PATTERN.sub(r"\1 ***", sanitized)
    sanitized = _BASIC_PATTERN.sub(r"\1 ***", sanitized)
    sanitized = _PASSWORD_ASSIGN_PATTERN.sub(r"\1=***", sanitized)
    sanitized = _JWT_PATTERN.sub(_REDACTED, sanitized)
    sanitized = _GROQ_KEY_PATTERN.sub(_REDACTED, sanitized)
    sanitized = _GITHUB_TOKEN_PATTERN.sub(_REDACTED, sanitized)

    for secret in secrets:
        if not secret:
            continue
        sanitized = sanitized.replace(secret, _REDACTED)
        # Also scrub URL-encoded forms when secrets appear in query strings.
        sanitized = sanitized.replace(secret.replace("/", "%2F"), _REDACTED)

    return sanitized


def sanitize_mapping(
    value: Any,
    *,
    secrets: Iterable[str] = (),
) -> Any:
    """Recursively scrub strings inside mappings/sequences for safe logging."""

    if isinstance(value, str):
        return sanitize_error_message(value, secrets=secrets)
    if isinstance(value, dict):
        return {
            str(key): sanitize_mapping(item, secrets=secrets)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_mapping(item, secrets=secrets) for item in value]
    return value


def safe_database_url_for_display(url: str) -> str:
    """Return a DSN with credentials removed for diagnostics."""

    try:
        parts = urlsplit(url)
    except ValueError:
        return redact_dsn(url)
    if not parts.username and not parts.password:
        return redact_dsn(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = host
    if parts.username:
        netloc = f"{parts.username}:{_REDACTED}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
