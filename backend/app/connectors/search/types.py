"""Shared query types for search index connectors."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.enums import Severity


class LogQueryFilters(BaseModel):
    """Time-range and attribute filters for log searches."""

    model_config = {"frozen": True}

    start: datetime
    end: datetime
    service: str | None = None
    environment: str | None = None
    severity: Severity | None = None
    size: int = Field(default=1000, ge=1, le=10_000)
