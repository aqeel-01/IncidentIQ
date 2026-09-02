"""Tests for investigation background jobs."""

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
from app.db.models import (
    Incident,
    InvestigationJobStatus,
    InvestigationStage,
    Organization,
    Project,
    Severity,
)
from app.db.models.investigation_job import InvestigationJob
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.investigation import (
    InvestigationJobRunner,
    InvestigationJobService,
    InvestigationOrchestrator,
    investigation_task_dispatcher,
)
from app.workers.tasks.investigation import run_investigation_job
from tests.test_investigation_pipeline import _synthetic_sources
from tests.test_rca_engine import SequentialFakeAIProvider, _staged_payloads


@pytest.fixture
def investigation_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        celery_task_max_retries=2,
    )


@pytest_asyncio.fixture
async def db_session(
    investigation_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        investigation_settings.database_url,
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


@pytest_asyncio.fixture
async def seeded_incident(db_session: AsyncSession) -> tuple[Project, Incident]:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    db_session.add(project)
    await db_session.flush()

    created = await IncidentService(db_session).create(
        CreateIncidentInput(
            project_id=project.id,
            title="Checkout failures",
            environment="production",
            severity=Severity.HIGH,
            started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()
    return project, created.incident


class RecordingDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[str] = []

    def dispatch(self, job_id: str) -> str:
        self.dispatched.append(job_id)
        return f"task-{job_id}"


@pytest.mark.asyncio
async def test_submit_investigation_job_queues_background_task(
    db_session: AsyncSession,
    seeded_incident: tuple[Project, Incident],
) -> None:
    project, incident = seeded_incident
    dispatcher = RecordingDispatcher()
    service = InvestigationJobService(db_session, dispatcher=dispatcher)

    snapshot = await service.submit(
        project_id=project.id,
        incident_id=incident.id,
    )
    await db_session.commit()

    assert snapshot.status is InvestigationJobStatus.QUEUED
    assert snapshot.stage is InvestigationStage.QUEUED
    assert snapshot.celery_task_id == f"task-{snapshot.id}"
    assert dispatcher.dispatched == [snapshot.id]


@pytest.mark.asyncio
async def test_investigation_job_runner_completes_pipeline(
    db_session: AsyncSession,
    investigation_settings: Settings,
    seeded_incident: tuple[Project, Incident],
) -> None:
    project, incident = seeded_incident
    job = InvestigationJob(
        id="job-1",
        project_id=project.id,
        incident_id=incident.id,
        status=InvestigationJobStatus.QUEUED,
        stage=InvestigationStage.QUEUED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()

    runner = InvestigationJobRunner(
        db_session,
        investigation_settings.model_copy(
            update={"rca_min_evidence_quality": 20, "rca_min_confidence": 0.6}
        ),
        sources=_synthetic_sources(),
        ai_provider=SequentialFakeAIProvider(_staged_payloads()),
    )
    result = await runner.run(job.id)

    assert result.status is InvestigationJobStatus.COMPLETED
    assert result.stage is InvestigationStage.COMPLETED
    assert job.attempt_count == 1
    assert job.started_at is not None
    assert job.completed_at is not None
    assert InvestigationStage.PERSIST_RCA.value in job.stage_artifacts


@pytest.mark.asyncio
async def test_investigation_job_runner_marks_failed_for_missing_incident(
    db_session: AsyncSession,
    investigation_settings: Settings,
    seeded_incident: tuple[Project, Incident],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, incident = seeded_incident
    job = InvestigationJob(
        id="job-2",
        project_id=project.id,
        incident_id=incident.id,
        status=InvestigationJobStatus.QUEUED,
        stage=InvestigationStage.QUEUED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()

    async def _missing_incident(_self, incident_id: int, project_id: int):
        return None

    monkeypatch.setattr(
        InvestigationOrchestrator,
        "_load_incident",
        _missing_incident,
    )

    runner = InvestigationJobRunner(db_session, investigation_settings)
    with pytest.raises(Exception, match="incident"):
        await runner.run(job.id)

    assert job.status is InvestigationJobStatus.FAILED
    assert job.stage is InvestigationStage.FAILED
    assert job.error_message is not None


@pytest.mark.asyncio
async def test_get_investigation_job_returns_snapshot(
    db_session: AsyncSession,
    seeded_incident: tuple[Project, Incident],
) -> None:
    project, incident = seeded_incident
    dispatcher = RecordingDispatcher()
    service = InvestigationJobService(db_session, dispatcher=dispatcher)
    submitted = await service.submit(project_id=project.id, incident_id=incident.id)
    await db_session.commit()

    loaded = await service.get(submitted.id)

    assert loaded is not None
    assert loaded.id == submitted.id
    assert loaded.status is InvestigationJobStatus.QUEUED


def test_run_investigation_job_task_delegates_to_session_runner(
    investigation_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _fake_run_with_session(settings, handler):
        calls.append("runner")
        return {
            "job_id": "job-eager",
            "incident_id": "1",
            "status": InvestigationJobStatus.COMPLETED.value,
            "stage": InvestigationStage.COMPLETED.value,
        }

    def _fake_run_async(coro):
        import asyncio

        return asyncio.run(coro)

    monkeypatch.setattr(
        "app.workers.tasks.investigation.run_with_session",
        _fake_run_with_session,
    )
    monkeypatch.setattr(
        "app.workers.tasks.investigation.run_async",
        _fake_run_async,
    )
    monkeypatch.setattr(
        "app.workers.tasks.investigation.get_settings",
        lambda: investigation_settings,
    )

    result = run_investigation_job.run("job-eager")

    assert calls == ["runner"]
    assert result["job_id"] == "job-eager"
    assert result["status"] == InvestigationJobStatus.COMPLETED.value


def test_investigation_task_dispatcher_wraps_callable() -> None:
    calls: list[str] = []

    def _dispatch(job_id: str) -> str:
        calls.append(job_id)
        return "task-123"

    dispatcher = investigation_task_dispatcher(_dispatch)
    task_id = dispatcher.dispatch("job-abc")

    assert calls == ["job-abc"]
    assert task_id == "task-123"
