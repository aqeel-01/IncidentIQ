"""Tests for historical RCA persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Organization, Project, Severity
from app.db.models.investigation_job import (
    InvestigationJob,
    InvestigationJobStatus,
    InvestigationStage,
)
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.rca import (
    HistoricalRCARecord,
    RCAEngineResult,
    RCAResult,
    RCAService,
    RCAStatus,
)
from app.domain.rca.types import Hypothesis


@pytest.fixture
def history_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
    )


@pytest_asyncio.fixture
async def db_session(
    history_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        history_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


def _engine_result(*, evidence_quality: int = 72) -> RCAEngineResult:
    return RCAEngineResult(
        result=RCAResult(
            status=RCAStatus.CONFIDENT,
            primary_hypothesis=Hypothesis(
                title="Deployment regression",
                description="Recent deployment preceded the first error spike.",
                confidence=0.82,
            ),
            confidence=0.82,
            evidence_quality=evidence_quality,
        ),
        engine_version="1",
        prompt_version="v1",
        ai_provider="ollama",
        ai_model="llama3.1:8b",
    )


async def _seed_incident(session: AsyncSession) -> tuple[Project, int]:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    session.add(project)
    await session.flush()

    created = await IncidentService(session).create(
        CreateIncidentInput(
            project_id=project.id,
            title="Checkout failures",
            environment="production",
            severity=Severity.HIGH,
            started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )
    )
    return project, created.incident.id


@pytest.mark.asyncio
async def test_persist_rca_stores_historical_metadata(
    db_session: AsyncSession,
) -> None:
    project, incident_id = await _seed_incident(db_session)
    job = InvestigationJob(
        id="history-job-1",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.COMPLETED,
        stage=InvestigationStage.COMPLETED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()

    row = await RCAService(db_session).persist(
        project_id=project.id,
        incident_id=incident_id,
        investigation_job_id=job.id,
        evidence_group_id=None,
        engine_result=_engine_result(evidence_quality=72),
    )
    job.rca_result_id = row.id
    await db_session.commit()

    record = await RCAService(db_session).get_record(row.id)

    assert record is not None
    assert record.investigation_job_id == "history-job-1"
    assert record.ai_provider == "ollama"
    assert record.ai_model == "llama3.1:8b"
    assert record.prompt_version == "v1"
    assert record.evidence_quality == 72
    assert record.status is RCAStatus.CONFIDENT
    assert record.result.primary_hypothesis is not None
    assert record.created_at is not None
    assert record.updated_at is not None


@pytest.mark.asyncio
async def test_get_for_investigation_returns_traceable_record(
    db_session: AsyncSession,
) -> None:
    project, incident_id = await _seed_incident(db_session)
    job = InvestigationJob(
        id="history-job-2",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.COMPLETED,
        stage=InvestigationStage.COMPLETED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()

    service = RCAService(db_session)
    row = await service.persist(
        project_id=project.id,
        incident_id=incident_id,
        investigation_job_id=job.id,
        evidence_group_id=None,
        engine_result=_engine_result(),
    )
    job.rca_result_id = row.id
    await db_session.commit()

    record = await service.get_for_investigation("history-job-2")

    assert isinstance(record, HistoricalRCARecord)
    assert record is not None
    assert record.id == row.id
    assert record.investigation_job_id == "history-job-2"


@pytest.mark.asyncio
async def test_list_for_incident_returns_newest_first(
    db_session: AsyncSession,
) -> None:
    project, incident_id = await _seed_incident(db_session)
    service = RCAService(db_session)

    first_job = InvestigationJob(
        id="history-job-3a",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.COMPLETED,
        stage=InvestigationStage.COMPLETED,
        stage_artifacts={},
    )
    second_job = InvestigationJob(
        id="history-job-3b",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.COMPLETED,
        stage=InvestigationStage.COMPLETED,
        stage_artifacts={},
    )
    db_session.add_all([first_job, second_job])
    await db_session.flush()

    await service.persist(
        project_id=project.id,
        incident_id=incident_id,
        investigation_job_id=first_job.id,
        evidence_group_id=None,
        engine_result=_engine_result(evidence_quality=40),
    )
    await service.persist(
        project_id=project.id,
        incident_id=incident_id,
        investigation_job_id=second_job.id,
        evidence_group_id=None,
        engine_result=_engine_result(evidence_quality=80),
    )
    await db_session.commit()

    records = await service.list_for_incident(incident_id)

    assert len(records) == 2
    assert records[0].investigation_job_id == "history-job-3b"
    assert records[1].investigation_job_id == "history-job-3a"
    assert records[0].evidence_quality == 80


@pytest.mark.asyncio
async def test_get_latest_for_incident_returns_most_recent_result(
    db_session: AsyncSession,
) -> None:
    project, incident_id = await _seed_incident(db_session)
    service = RCAService(db_session)

    for index, quality in enumerate((30, 90), start=1):
        job = InvestigationJob(
            id=f"history-job-4{index}",
            project_id=project.id,
            incident_id=incident_id,
            status=InvestigationJobStatus.COMPLETED,
            stage=InvestigationStage.COMPLETED,
            stage_artifacts={},
        )
        db_session.add(job)
        await db_session.flush()
        await service.persist(
            project_id=project.id,
            incident_id=incident_id,
            investigation_job_id=job.id,
            evidence_group_id=None,
            engine_result=_engine_result(evidence_quality=quality),
        )

    await db_session.commit()

    latest = await service.get_latest_for_incident(incident_id)

    assert latest is not None
    assert latest.evidence_quality == 90
