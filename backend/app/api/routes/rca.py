"""Persisted root cause analysis API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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
) -> HistoricalRCARecord:
    records = await RCAService(session).list_for_incident(incident_id)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RCA for incident {incident_id} not found",
        )
    return records[0]
