"""Alert webhook API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.alertmanager import (
    AlertmanagerWebhookError,
    AlertmanagerWebhookPayload,
    AlertmanagerWebhookService,
)
from app.domain.events import AlertStatus

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class AlertIncidentOutcomeResponse(BaseModel):
    alert_name: str
    alert_status: AlertStatus
    incident_id: int | None
    action: str


class AlertmanagerWebhookResponse(BaseModel):
    alerts_received: int
    incidents_created: int
    incidents_merged: int
    incidents_resolved: int
    outcomes: list[AlertIncidentOutcomeResponse]


@router.post(
    "/prometheus",
    response_model=AlertmanagerWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def prometheus_alertmanager_webhook(
    payload: AlertmanagerWebhookPayload,
    session: SessionDep,
    project_id: Annotated[int, Query(description="Project that owns ingested alerts")],
) -> AlertmanagerWebhookResponse:
    """Accept an Alertmanager webhook and create or update incidents."""

    service = AlertmanagerWebhookService(session)
    try:
        result = await service.ingest(project_id=project_id, payload=payload)
        await session.commit()
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AlertmanagerWebhookError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return AlertmanagerWebhookResponse(
        alerts_received=result.alerts_received,
        incidents_created=result.incidents_created,
        incidents_merged=result.incidents_merged,
        incidents_resolved=result.incidents_resolved,
        outcomes=[
            AlertIncidentOutcomeResponse(
                alert_name=outcome.alert_name,
                alert_status=outcome.alert_status,
                incident_id=outcome.incident_id,
                action=outcome.action,
            )
            for outcome in result.outcomes
        ],
    )
