"""Incident timeline API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import Severity
from app.db.session import get_db
from app.domain.timeline import TimelineService
from app.domain.timeline.types import TimelineCategory, TimelineEntry, TimelineMarkers

router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class TimelineEntryResponse(BaseModel):
    id: str
    category: TimelineCategory
    timestamp: datetime
    title: str
    summary: str | None = None
    severity: Severity | None = None
    event_id: int | None = None
    error_group_id: int | None = None
    metadata: dict[str, Any]

    model_config = ConfigDict(frozen=True)


class TimelineMarkersResponse(BaseModel):
    first_anomaly: TimelineEntryResponse | None = None
    first_relevant_error: TimelineEntryResponse | None = None
    first_alert: TimelineEntryResponse | None = None
    recent_deployment: TimelineEntryResponse | None = None
    recovery: TimelineEntryResponse | None = None

    model_config = ConfigDict(frozen=True)


class TimelineResponse(BaseModel):
    incident_id: int
    project_id: int
    started_at: datetime
    ended_at: datetime | None
    window_start: datetime
    window_end: datetime
    entries: list[TimelineEntryResponse]
    markers: TimelineMarkersResponse
    counts: dict[str, int]

    model_config = ConfigDict(frozen=True)


def _entry_response(entry: TimelineEntry | None) -> TimelineEntryResponse | None:
    if entry is None:
        return None
    return TimelineEntryResponse(
        id=entry.id,
        category=entry.category,
        timestamp=entry.timestamp,
        title=entry.title,
        summary=entry.summary,
        severity=entry.severity,
        event_id=entry.event_id,
        error_group_id=entry.error_group_id,
        metadata=entry.metadata,
    )


def _markers_response(markers: TimelineMarkers) -> TimelineMarkersResponse:
    return TimelineMarkersResponse(
        first_anomaly=_entry_response(markers.first_anomaly),
        first_relevant_error=_entry_response(markers.first_relevant_error),
        first_alert=_entry_response(markers.first_alert),
        recent_deployment=_entry_response(markers.recent_deployment),
        recovery=_entry_response(markers.recovery),
    )


@router.get("/{incident_id}", response_model=TimelineResponse)
async def get_incident_timeline(
    incident_id: int,
    session: SessionDep,
) -> TimelineResponse:
    result = await TimelineService(session).build(incident_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident {incident_id} not found",
        )

    return TimelineResponse(
        incident_id=result.incident_id,
        project_id=result.project_id,
        started_at=result.started_at,
        ended_at=result.ended_at,
        window_start=result.window_start,
        window_end=result.window_end,
        entries=[
            entry
            for entry in (
                _entry_response(item) for item in result.entries
            )
            if entry is not None
        ],
        markers=_markers_response(result.markers),
        counts=result.counts,
    )
