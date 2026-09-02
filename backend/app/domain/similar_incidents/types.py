"""Types for similar incident retrieval."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IncidentSimilarityProfile(BaseModel):
    """Structured incident information used for similarity scoring."""

    model_config = ConfigDict(frozen=True)

    incident_id: int
    project_id: int
    title: str
    problem_identity: str
    fingerprint: str
    environment: str
    service_id: int | None = None
    service_name: str | None = None
    severity: str
    status: str
    started_at: datetime
    error_group_titles: list[str] = Field(default_factory=list)
    symptom_titles: list[str] = Field(default_factory=list)
    primary_hypothesis_title: str | None = None
    embedding_text: str = ""


class SimilarIncidentMatch(BaseModel):
    """A scored historical incident candidate."""

    model_config = ConfigDict(frozen=True)

    incident_id: int
    title: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    environment: str
    service: str | None = None
    status: str
    started_at: datetime
    primary_hypothesis_title: str | None = None
    matching_signals: list[str] = Field(default_factory=list)
    context_only: bool = True
