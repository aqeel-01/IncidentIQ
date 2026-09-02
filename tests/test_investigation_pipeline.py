"""End-to-end investigation pipeline tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    EvidenceGroup,
    InvestigationJob,
    InvestigationJobStatus,
    InvestigationStage,
    Organization,
    Project,
    RCAResultRecord,
    Service,
    Severity,
)
from app.domain.events import (
    AlertEvent,
    AlertStatus,
    DeploymentEvent,
    LogEvent,
    MetricEvent,
)
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.investigation import (
    InvestigationJobRunner,
    InvestigationOrchestrator,
    InvestigationSources,
)
from app.domain.rca import RCAStatus
from tests.test_rca_engine import SequentialFakeAIProvider, _staged_payloads


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _base_event_fields() -> dict:
    return {
        "source": "synthetic",
        "source_type": "test",
        "environment": "production",
        "raw_data": {"seed": True},
    }


def _synthetic_sources() -> InvestigationSources:
    return InvestigationSources(
        canonical_events=(
            DeploymentEvent(
                timestamp=_ts(-60),
                version="v1.2.2",
                commit_sha="deploy123",
                repository="payments-api",
                service="payments-api",
                source="azure_devops:pipelines",
                source_type="azure_devops",
                environment="production",
                raw_data={"seed": True},
            ),
            MetricEvent(
                timestamp=_ts(-10),
                metric_name="error_rate",
                value=0.9,
                service="payments-api",
                **_base_event_fields(),
            ),
            LogEvent(
                timestamp=_ts(0),
                message="connection timeout talking to database",
                severity=Severity.HIGH,
                service="payments-api",
                **_base_event_fields(),
            ),
            AlertEvent(
                timestamp=_ts(5),
                name="HighErrorRate",
                status=AlertStatus.FIRING,
                severity=Severity.HIGH,
                service="payments-api",
                **_base_event_fields(),
            ),
        ),
        raw_log_lines=(
            "2026-09-01T12:00:00Z ERROR connection timeout talking to database",
        ),
    )


@pytest.fixture
def pipeline_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        rca_min_evidence_quality=20,
        rca_min_confidence=0.6,
    )


@pytest_asyncio.fixture
async def db_session(pipeline_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        pipeline_settings.database_url,
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


async def _seed_incident(session: AsyncSession) -> tuple[Project, Service, int]:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    session.add(project)
    await session.flush()

    incident = await IncidentService(session).create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="Checkout failures",
            environment="production",
            severity=Severity.HIGH,
            started_at=_ts(0),
        )
    )
    await session.commit()
    return project, service, incident.incident.id


@pytest.mark.asyncio
async def test_investigation_pipeline_end_to_end(
    db_session: AsyncSession,
    pipeline_settings: Settings,
) -> None:
    project, _service, incident_id = await _seed_incident(db_session)
    job = InvestigationJob(
        id="pipeline-job-1",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.QUEUED,
        stage=InvestigationStage.QUEUED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()

    provider = SequentialFakeAIProvider(_staged_payloads())
    orchestrator = InvestigationOrchestrator(
        db_session,
        pipeline_settings,
        sources=_synthetic_sources(),
        ai_provider=provider,
    )

    result = await orchestrator.run(job.id)
    await db_session.commit()

    assert result.status is InvestigationJobStatus.COMPLETED
    assert result.stage is InvestigationStage.COMPLETED

    refreshed_job = await db_session.get(InvestigationJob, job.id)
    assert refreshed_job is not None
    assert refreshed_job.stage_artifacts
    assert InvestigationStage.PERSIST_RCA.value in refreshed_job.stage_artifacts

    evidence_count = await db_session.scalar(
        select(EvidenceGroup.id).where(EvidenceGroup.incident_id == incident_id)
    )
    assert evidence_count is not None

    rca_row = await db_session.scalar(
        select(RCAResultRecord).where(RCAResultRecord.incident_id == incident_id)
    )
    assert rca_row is not None
    assert rca_row.status == RCAStatus.CONFIDENT.value
    assert rca_row.investigation_job_id == job.id
    assert rca_row.ai_provider == "ollama"
    assert rca_row.ai_model == "fake-rca-model"
    assert rca_row.prompt_version is not None
    assert rca_row.evidence_quality >= 0
    assert refreshed_job.rca_result_id == rca_row.id
    assert len(provider.generate_calls) == 4


@pytest.mark.asyncio
async def test_investigation_pipeline_resumes_from_checkpoint(
    db_session: AsyncSession,
    pipeline_settings: Settings,
) -> None:
    project, _service, incident_id = await _seed_incident(db_session)
    job = InvestigationJob(
        id="pipeline-job-2",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.QUEUED,
        stage=InvestigationStage.GROUP_ERRORS,
        stage_artifacts={
            InvestigationStage.COLLECT_SOURCES.value: {"canonical_events": 4},
            InvestigationStage.PARSE.value: {"parsed_records": 1},
            InvestigationStage.NORMALIZE.value: {
                "normalized_records": 1,
                "canonical_events": 4,
            },
            InvestigationStage.DEDUPLICATE.value: {"kept": 1, "removed": 0},
        },
    )
    db_session.add(job)
    await db_session.flush()

    provider = SequentialFakeAIProvider(_staged_payloads())
    orchestrator = InvestigationOrchestrator(
        db_session,
        pipeline_settings,
        sources=_synthetic_sources(),
        ai_provider=provider,
    )

    result = await orchestrator.run(job.id)

    assert result.status is InvestigationJobStatus.COMPLETED
    assert InvestigationStage.COLLECT_SOURCES.value in job.stage_artifacts


@pytest.mark.asyncio
async def test_investigation_job_runner_executes_pipeline(
    db_session: AsyncSession,
    pipeline_settings: Settings,
) -> None:
    project, _service, incident_id = await _seed_incident(db_session)
    job = InvestigationJob(
        id="pipeline-job-3",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.QUEUED,
        stage=InvestigationStage.QUEUED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()

    runner = InvestigationJobRunner(
        db_session,
        pipeline_settings,
        sources=_synthetic_sources(),
        ai_provider=SequentialFakeAIProvider(_staged_payloads()),
    )
    result = await runner.run(job.id)

    assert result.status is InvestigationJobStatus.COMPLETED
