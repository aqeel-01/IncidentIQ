"""Persist RCA engine outputs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rca_result import RCAResultRecord
from app.domain.rca.engine import RCAEngineResult
from app.domain.rca.types import HistoricalRCARecord, RCAResult, RCAStatus


class RCAService:
    """Persist and query structured RCA results."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist(
        self,
        *,
        project_id: int,
        incident_id: int,
        investigation_job_id: str | None,
        evidence_group_id: int | None,
        engine_result: RCAEngineResult,
    ) -> RCAResultRecord:
        row = RCAResultRecord(
            project_id=project_id,
            incident_id=incident_id,
            investigation_job_id=investigation_job_id,
            evidence_group_id=evidence_group_id,
            status=engine_result.result.status.value,
            confidence=engine_result.result.confidence,
            evidence_quality=engine_result.result.evidence_quality,
            ai_provider=engine_result.ai_provider,
            ai_model=engine_result.ai_model,
            engine_version=engine_result.engine_version,
            prompt_version=engine_result.prompt_version,
            result_data=engine_result.result.model_dump(mode="json"),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_record(self, record_id: int) -> HistoricalRCARecord | None:
        row = await self._session.get(RCAResultRecord, record_id)
        if row is None:
            return None
        return _to_historical_record(row)

    async def get_for_investigation(
        self,
        investigation_job_id: str,
    ) -> HistoricalRCARecord | None:
        result = await self._session.execute(
            select(RCAResultRecord).where(
                RCAResultRecord.investigation_job_id == investigation_job_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_historical_record(row)

    async def list_for_incident(self, incident_id: int) -> list[HistoricalRCARecord]:
        result = await self._session.execute(
            select(RCAResultRecord)
            .where(RCAResultRecord.incident_id == incident_id)
            .order_by(
                RCAResultRecord.created_at.desc(),
                RCAResultRecord.id.desc(),
            )
        )
        return [_to_historical_record(row) for row in result.scalars().all()]

    async def get_latest_for_incident(self, incident_id: int) -> RCAResult | None:
        records = await self.list_for_incident(incident_id)
        if not records:
            return None
        return records[0].result


def _to_historical_record(row: RCAResultRecord) -> HistoricalRCARecord:
    return HistoricalRCARecord(
        id=row.id,
        project_id=row.project_id,
        incident_id=row.incident_id,
        investigation_job_id=row.investigation_job_id,
        evidence_group_id=row.evidence_group_id,
        status=RCAStatus(row.status),
        confidence=row.confidence,
        evidence_quality=row.evidence_quality,
        ai_provider=row.ai_provider,
        ai_model=row.ai_model,
        engine_version=row.engine_version,
        prompt_version=row.prompt_version,
        result=RCAResult.model_validate(row.result_data),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
