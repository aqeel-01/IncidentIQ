"""Incident API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUserDep,
    InvestigationDispatcherDep,
    SettingsDep,
    require_project_role,
)
from app.api.routes.investigations import (
    InvestigationResponse,
    to_investigation_response,
)
from app.db.models.enums import IncidentStatus, ProjectRole, Severity
from app.db.session import get_db
from app.domain.incidents import (
    CreateIncidentInput,
    IncidentCreateAction,
    IncidentCreateResult,
    IncidentListFilters,
    IncidentService,
    IncidentSummary,
    IncidentValidationError,
)
from app.domain.investigation import InvestigationJobService

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class CreateIncidentRequest(BaseModel):
    project_id: int
    title: str = Field(min_length=1, max_length=500)
    environment: str = Field(min_length=1, max_length=100)
    severity: Severity
    service_id: int | None = None
    status: IncidentStatus = IncidentStatus.OPEN
    started_at: datetime | None = None
    ended_at: datetime | None = None
    occurrence_count: int = Field(default=1, ge=1)


class IncidentResponse(BaseModel):
    id: int
    project_id: int
    service_id: int | None
    title: str
    environment: str
    severity: Severity
    status: IncidentStatus
    started_at: datetime
    ended_at: datetime | None
    occurrence_count: int
    fingerprint: str
    created_at: datetime
    updated_at: datetime
    deduplicated: bool = False

    model_config = {"from_attributes": True}


class CreateIncidentResponse(IncidentResponse):
    action: IncidentCreateAction


class IncidentListResponse(BaseModel):
    items: list[IncidentResponse]
    total: int
    page: int
    page_size: int


class IncidentSummaryResponse(BaseModel):
    project_id: int
    total: int
    active: int
    critical_active: int
    recent: int
    recent_window_hours: int
    by_status: dict[IncidentStatus, int]
    by_severity: dict[Severity, int]


def _to_response(incident) -> IncidentResponse:
    return IncidentResponse.model_validate(incident)


def _to_create_response(result: IncidentCreateResult) -> CreateIncidentResponse:
    data = IncidentResponse.model_validate(result.incident).model_dump(
        exclude={"deduplicated"}
    )
    return CreateIncidentResponse(
        action=result.action,
        deduplicated=result.action is IncidentCreateAction.MERGED,
        **data,
    )


@router.post(
    "",
    response_model=CreateIncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_incident(
    body: CreateIncidentRequest,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> CreateIncidentResponse:
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=body.project_id,
        minimum_role=ProjectRole.ENGINEER,
    )
    service = IncidentService(session)
    try:
        result = await service.create(CreateIncidentInput(**body.model_dump()))
        await session.commit()
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except IncidentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _to_create_response(result)


@router.post(
    "/{incident_id}/investigate",
    response_model=InvestigationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def investigate_incident(
    incident_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    dispatcher: InvestigationDispatcherDep,
) -> InvestigationResponse:
    incident = await IncidentService(session).get_by_id(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident {incident_id} not found",
        )
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=incident.project_id,
        minimum_role=ProjectRole.ENGINEER,
    )

    service = InvestigationJobService(session, dispatcher=dispatcher)
    try:
        snapshot = await service.submit_for_incident(incident_id)
        await session.commit()
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return to_investigation_response(snapshot)


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    project_id: Annotated[int, Query(description="Project to list incidents for")],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    severity: Annotated[
        list[Severity] | None,
        Query(description="Filter by one or more severities"),
    ] = None,
    status_filter: Annotated[
        list[IncidentStatus] | None,
        Query(alias="status", description="Filter by one or more statuses"),
    ] = None,
) -> IncidentListResponse:
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=project_id,
        minimum_role=ProjectRole.VIEWER,
    )
    service = IncidentService(session)
    try:
        result = await service.list(
            IncidentListFilters(
                project_id=project_id,
                page=page,
                page_size=page_size,
                severities=tuple(severity) if severity else None,
                statuses=tuple(status_filter) if status_filter else None,
            )
        )
    except IncidentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return IncidentListResponse(
        items=[_to_response(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/summary", response_model=IncidentSummaryResponse)
async def get_incident_summary(
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    project_id: Annotated[int, Query(description="Project to summarize")],
    recent_hours: Annotated[
        int,
        Query(ge=1, le=24 * 30, description="Window for 'recent' incidents"),
    ] = 24,
) -> IncidentSummaryResponse:
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=project_id,
        minimum_role=ProjectRole.VIEWER,
    )
    try:
        summary = await IncidentService(session).summarize(
            project_id,
            recent_window_hours=recent_hours,
        )
    except IncidentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _to_summary_response(summary)


def _to_summary_response(summary: IncidentSummary) -> IncidentSummaryResponse:
    return IncidentSummaryResponse(
        project_id=summary.project_id,
        total=summary.total,
        active=summary.active,
        critical_active=summary.critical_active,
        recent=summary.recent,
        recent_window_hours=summary.recent_window_hours,
        by_status=summary.by_status,
        by_severity=summary.by_severity,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> IncidentResponse:
    incident = await IncidentService(session).get_by_id(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident {incident_id} not found",
        )
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=incident.project_id,
        minimum_role=ProjectRole.VIEWER,
    )
    return _to_response(incident)
