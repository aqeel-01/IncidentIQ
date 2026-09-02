"""Investigation job domain types."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.investigation_job import InvestigationJobStatus, InvestigationStage


class InvestigationProgress(BaseModel):
    """Pipeline progress derived from completed stage artifacts."""

    model_config = ConfigDict(frozen=True)

    completed_stages: list[str]
    total_stages: int = Field(ge=0)
    percent_complete: int = Field(ge=0, le=100)


class InvestigationJobSnapshot(BaseModel):
    """Public view of an investigation job."""

    model_config = ConfigDict(frozen=True)

    id: str
    project_id: int
    incident_id: int
    status: InvestigationJobStatus
    stage: InvestigationStage
    stage_artifacts: dict[str, object] = Field(default_factory=dict)
    celery_task_id: str | None = None
    attempt_count: int = Field(ge=0)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InvestigationJobResult(BaseModel):
    """Outcome of running an investigation job."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    incident_id: int
    status: InvestigationJobStatus
    stage: InvestigationStage


class InvestigationJobError(RuntimeError):
    """Raised when an investigation job cannot be executed."""
