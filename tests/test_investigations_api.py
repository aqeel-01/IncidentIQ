"""Tests for the investigation API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_investigation_dispatcher
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import (
    InvestigationJobStatus,
    InvestigationStage,
    Project,
    Severity,
)
from app.db.models.enums import ProjectRole
from app.db.models.investigation_job import InvestigationJob
from app.db.session import get_db
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.investigation.stages import PIPELINE_STAGE_ORDER
from app.main import create_app
from tests.auth_support import create_principal, grant_role, install_current_user


class RecordingDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[str] = []

    def dispatch(self, job_id: str) -> str:
        self.dispatched.append(job_id)
        return f"task-{job_id}"


@pytest.fixture
def investigation_api_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
    )


@pytest.fixture
def recording_dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest_asyncio.fixture
async def db_session(
    investigation_api_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        investigation_api_settings.database_url,
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


@pytest.fixture
def api_client(
    investigation_api_settings: Settings,
    db_session: AsyncSession,
    recording_dispatcher: RecordingDispatcher,
    principal,
) -> Iterator[TestClient]:
    app = create_app(settings=investigation_api_settings)
    app.dependency_overrides[get_settings] = lambda: investigation_api_settings
    app.dependency_overrides[get_investigation_dispatcher] = lambda: (
        recording_dispatcher
    )

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    install_current_user(app, principal)

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def principal(db_session: AsyncSession):
    return await create_principal(db_session)


@pytest_asyncio.fixture
async def seeded_incident(
    db_session: AsyncSession,
    principal,
) -> tuple[Project, int]:
    project = Project(
        name="Payments",
        slug="payments",
        organization_id=principal.organization_id,
    )
    db_session.add(project)
    await db_session.flush()
    await grant_role(db_session, principal, project, ProjectRole.ADMIN)

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
    return project, created.incident.id


def test_investigate_incident_returns_queued_without_blocking(
    api_client: TestClient,
    seeded_incident: tuple[Project, int],
    recording_dispatcher: RecordingDispatcher,
) -> None:
    _project, incident_id = seeded_incident

    response = api_client.post(f"/api/v1/incidents/{incident_id}/investigate")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["stage"] == InvestigationStage.QUEUED.value
    assert body["incident_id"] == incident_id
    assert body["progress"]["percent_complete"] == 0
    assert body["progress"]["completed_stages"] == []
    assert body["progress"]["total_stages"] == len(PIPELINE_STAGE_ORDER)
    assert body["celery_task_id"] == f"task-{body['id']}"
    assert recording_dispatcher.dispatched == [body["id"]]


def test_investigate_incident_returns_404_for_missing_incident(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/v1/incidents/999/investigate")

    assert response.status_code == 404
    assert "incident 999 not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_investigation_returns_status_and_progress(
    api_client: TestClient,
    db_session: AsyncSession,
    seeded_incident: tuple[Project, int],
) -> None:
    project, incident_id = seeded_incident
    job = InvestigationJob(
        id="job-progress",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.RUNNING,
        stage=InvestigationStage.BUILD_TIMELINE,
        stage_artifacts={
            InvestigationStage.COLLECT_SOURCES.value: {"canonical_events": 2},
            InvestigationStage.PARSE.value: {"parsed_records": 1},
            InvestigationStage.NORMALIZE.value: {"normalized_records": 1},
            InvestigationStage.DEDUPLICATE.value: {"kept": 1, "removed": 0},
            InvestigationStage.GROUP_ERRORS.value: {"ingested_event_ids": [1]},
        },
        celery_task_id="task-job-progress",
        attempt_count=1,
        started_at=datetime(2026, 9, 1, 12, 1, tzinfo=UTC),
    )
    db_session.add(job)
    await db_session.commit()

    response = api_client.get("/api/v1/investigations/job-progress")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["stage"] == InvestigationStage.BUILD_TIMELINE.value
    assert body["progress"]["completed_stages"] == [
        stage.value for stage in PIPELINE_STAGE_ORDER[:5]
    ]
    assert body["progress"]["total_stages"] == len(PIPELINE_STAGE_ORDER)
    assert body["progress"]["percent_complete"] == int(
        round(5 / len(PIPELINE_STAGE_ORDER) * 100)
    )


@pytest.mark.asyncio
async def test_get_investigation_returns_completed_status(
    api_client: TestClient,
    db_session: AsyncSession,
    seeded_incident: tuple[Project, int],
) -> None:
    project, incident_id = seeded_incident
    artifacts = {stage.value: {"done": True} for stage in PIPELINE_STAGE_ORDER}
    job = InvestigationJob(
        id="job-complete",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.COMPLETED,
        stage=InvestigationStage.COMPLETED,
        stage_artifacts=artifacts,
        celery_task_id="task-job-complete",
        attempt_count=1,
        started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, 12, 5, tzinfo=UTC),
    )
    db_session.add(job)
    await db_session.commit()

    response = api_client.get("/api/v1/investigations/job-complete")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["stage"] == InvestigationStage.COMPLETED.value
    assert body["progress"]["percent_complete"] == 100


@pytest.mark.asyncio
async def test_get_investigation_returns_failed_status(
    api_client: TestClient,
    db_session: AsyncSession,
    seeded_incident: tuple[Project, int],
) -> None:
    project, incident_id = seeded_incident
    job = InvestigationJob(
        id="job-failed",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.FAILED,
        stage=InvestigationStage.FAILED,
        stage_artifacts={
            InvestigationStage.COLLECT_SOURCES.value: {"canonical_events": 0},
        },
        error_message="timeline could not be built",
        attempt_count=1,
        started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, 12, 2, tzinfo=UTC),
    )
    db_session.add(job)
    await db_session.commit()

    response = api_client.get("/api/v1/investigations/job-failed")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["stage"] == InvestigationStage.FAILED.value
    assert body["error_message"] == "timeline could not be built"


def test_get_investigation_returns_404_for_missing_job(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/investigations/does-not-exist")

    assert response.status_code == 404
    assert "investigation does-not-exist not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_latest_investigation_for_incident(
    api_client: TestClient,
    db_session: AsyncSession,
    seeded_incident: tuple[Project, int],
) -> None:
    project, incident_id = seeded_incident
    job = InvestigationJob(
        id="latest-job",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.RUNNING,
        stage=InvestigationStage.BUILD_EVIDENCE,
        stage_artifacts={
            stage.value: {"done": True} for stage in PIPELINE_STAGE_ORDER[:9]
        },
        attempt_count=1,
    )
    db_session.add(job)
    await db_session.commit()

    response = api_client.get(
        f"/api/v1/investigations/by-incident/{incident_id}/latest"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "latest-job"
    assert body["incident_id"] == incident_id
    assert body["stage"] == InvestigationStage.BUILD_EVIDENCE.value


def test_get_latest_investigation_returns_404_when_not_started(
    api_client: TestClient,
    seeded_incident: tuple[Project, int],
) -> None:
    _project, incident_id = seeded_incident

    response = api_client.get(
        f"/api/v1/investigations/by-incident/{incident_id}/latest"
    )

    assert response.status_code == 404
    assert (
        f"investigation for incident {incident_id} not found"
        in (response.json()["detail"])
    )
