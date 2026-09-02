"""Shared types for log format detection and parsing."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models.enums import Severity


class LogFormat(enum.StrEnum):
    PLAIN_TEXT = "plain_text"
    STRUCTURED_TEXT = "structured_text"
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"


class ParsedLogRecord(BaseModel):
    """A single parsed log line/record with normalized common fields."""

    model_config = {"frozen": True}

    line_number: int
    format: LogFormat
    timestamp: datetime | None = None
    severity: Severity | None = None
    message: str | None = None
    service: str | None = None
    host: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class DetectionResult(BaseModel):
    """Outcome of automatic format detection."""

    model_config = {"frozen": True}

    format: LogFormat
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class ParseStats(BaseModel):
    """Summary counters for a parse run."""

    model_config = {"frozen": True}

    format: LogFormat
    records_parsed: int = 0
    records_skipped: int = 0
