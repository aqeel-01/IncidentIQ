"""Investigation job API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.investigation_job import InvestigationJobStatus
from app.db.session import get_db
from app.domain.investigation import (
    InvestigationJobService,
    InvestigationJobSnapshot,
    investigation_progress,
)

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]

InvestigationStatusResponse = Literal[
    "queued",
    "running",
    "completed",
    "failed",
]


class InvestigationProgressResponse(BaseModel):
    completed_stages: list[str]
    total_stages: int = Field(ge=0)
    percent_complete: int = Field(ge=0, le=100)

    model_config = ConfigDict(frozen=True)


class InvestigationResponse(BaseModel):
    id: str
    incident_id: int
    project_id: int
    status: InvestigationStatusResponse
    stage: str
    progress: InvestigationProgressResponse
    attempt_count: int = Field(ge=0)
    error_message: str | None = None
    celery_task_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


def _api_status(status: InvestigationJobStatus) -> InvestigationStatusResponse:
    if status is InvestigationJobStatus.RETRYING:
        return "running"
    return status.value.lower()  # type: ignore[return-value]


def to_investigation_response(
    snapshot: InvestigationJobSnapshot,
) -> InvestigationResponse:
    completed, total, percent = investigation_progress(snapshot.stage_artifacts)
    return InvestigationResponse(
        id=snapshot.id,
        incident_id=snapshot.incident_id,
        project_id=snapshot.project_id,
        status=_api_status(snapshot.status),
        stage=snapshot.stage.value,
        progress=InvestigationProgressResponse(
            completed_stages=completed,
            total_stages=total,
            percent_complete=percent,
        ),
        attempt_count=snapshot.attempt_count,
        error_message=snapshot.error_message,
        celery_task_id=snapshot.celery_task_id,
        started_at=snapshot.started_at,
        completed_at=snapshot.completed_at,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
    )


@router.get(
    "/by-incident/{incident_id}/latest",
    response_model=InvestigationResponse,
)
async def get_latest_investigation_for_incident(
    incident_id: int,
    session: SessionDep,
) -> InvestigationResponse:
    snapshot = await InvestigationJobService(session).get_latest_for_incident(
        incident_id
    )
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"investigation for incident {incident_id} not found",
        )
    return to_investigation_response(snapshot)


@router.get("/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(
    investigation_id: str,
    session: SessionDep,
) -> InvestigationResponse:
    snapshot = await InvestigationJobService(session).get(investigation_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"investigation {investigation_id} not found",
        )
    return to_investigation_response(snapshot)
