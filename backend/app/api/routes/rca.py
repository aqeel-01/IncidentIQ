"""Persisted root cause analysis API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SettingsDep, require_project_role
from app.db.models.enums import ProjectRole
from app.db.session import get_db
from app.domain.rca.service import RCAService
from app.domain.rca.types import HistoricalRCARecord

router = APIRouter(prefix="/api/v1/rca", tags=["rca"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/incidents/{incident_id}/latest",
    response_model=HistoricalRCARecord,
)
async def get_latest_rca_for_incident(
    incident_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
) -> HistoricalRCARecord:
    records = await RCAService(session).list_for_incident(incident_id)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RCA for incident {incident_id} not found",
        )
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=records[0].project_id,
        minimum_role=ProjectRole.VIEWER,
    )
    return records[0]
