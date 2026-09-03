"""Structured (JSON) logging configuration.

Emitting logs as JSON keeps them machine-parseable for aggregation. Messages and
exception text are scrubbed through central secret redaction before emission.
Configuration is idempotent so it can be safely called on every startup.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.core.security import sanitize_error_message, sanitize_mapping

_CONFIGURED = False

# Attributes present on every ``LogRecord``; anything else is treated as
# structured context supplied via ``logger.info(..., extra={...})``.
_RESERVED_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON documents with secrets redacted."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_error_message(record.getMessage()),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = sanitize_mapping(value)

        if record.exc_info:
            payload["exc_info"] = sanitize_error_message(
                self.formatException(record.exc_info)
            )

        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger exactly once."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    _CONFIGURED = True


def reset_logging_for_tests() -> None:
    """Allow tests to reinstall logging configuration."""

    global _CONFIGURED
    _CONFIGURED = False
