"""Types produced by the log normalization stage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models.enums import Severity
from app.domain.parsing.types import LogFormat


class NormalizedLogRecord(BaseModel):
    """A parsed log record with normalized fields for downstream grouping.

    ``message`` retains a whitespace-cleaned original; ``normalized_message``
    contains dynamic-value placeholders for fingerprinting. ``raw_data`` is never
    modified.
    """

    model_config = {"frozen": True}

    line_number: int
    format: LogFormat
    timestamp: datetime | None = None
    severity: Severity | None = None
    message: str | None = None
    normalized_message: str | None = None
    service: str | None = None
    host: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    environment: str | None = None
    normalized_data: dict[str, Any] = Field(default_factory=dict)
    raw_data: dict[str, Any] = Field(default_factory=dict)
