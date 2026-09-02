"""Types for error-group deduplication."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.enums import EventType, Severity


class MergeAction(enum.StrEnum):
    CREATED = "CREATED"
    MERGED = "MERGED"


class SimilarityClassification(enum.StrEnum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    NO_MATCH = "NO_MATCH"


class ErrorGroupEventInput(BaseModel):
    """Normalized event data used to find or update a logical error group."""

    model_config = {"frozen": True}

    project_id: int
    timestamp: datetime
    severity: Severity
    normalized_message: str = Field(min_length=1)
    service_id: int | None = None
    service: str | None = None
    source: str = Field(min_length=1)
    event_type: EventType = EventType.LOG


class SimilarityMatchSummary(BaseModel):
    """Similarity metadata attached to a merge outcome."""

    model_config = {"frozen": True}

    matched_error_group_id: int
    normalized_message: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    classification: SimilarityClassification


class ErrorGroupMergeResult(BaseModel):
    """Outcome of merging an event into the error-group store."""

    model_config = {"frozen": True}

    action: MergeAction
    error_group_id: int
    fingerprint: str
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime
    similarity_match: SimilarityMatchSummary | None = None
    investigation_candidate: SimilarityMatchSummary | None = None
