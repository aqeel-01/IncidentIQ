"""Tests for persisted RCA API responses."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import Organization
from app.db.models.enums import ProjectRole
from app.db.models.investigation_job import (
    InvestigationJob,
    InvestigationJobStatus,
    InvestigationStage,
)
from app.db.session import get_db
from app.domain.rca import RCAService
from app.main import create_app
from tests.auth_support import create_principal, grant_role, install_current_user
from tests.test_rca_history import _engine_result, _seed_incident


@pytest.fixture
def rca_api_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
    )


@pytest_asyncio.fixture
async def db_session(
    rca_api_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        rca_api_settings.database_url,
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
    rca_api_settings: Settings,
    db_session: AsyncSession,
    principal,
) -> Iterator[TestClient]:
    app = create_app(settings=rca_api_settings)
    app.dependency_overrides[get_settings] = lambda: rca_api_settings

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


@pytest.mark.asyncio
async def test_get_latest_rca_for_incident(
    api_client: TestClient,
    db_session: AsyncSession,
    principal,
) -> None:
    org = await db_session.get(Organization, principal.organization_id)
    project, incident_id = await _seed_incident(db_session, organization=org)
    await grant_role(db_session, principal, project, ProjectRole.ADMIN)
    job = InvestigationJob(
        id="rca-api-job",
        project_id=project.id,
        incident_id=incident_id,
        status=InvestigationJobStatus.COMPLETED,
        stage=InvestigationStage.COMPLETED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()
    await RCAService(db_session).persist(
        project_id=project.id,
        incident_id=incident_id,
        investigation_job_id=job.id,
        evidence_group_id=None,
        engine_result=_engine_result(evidence_quality=84),
    )
    await db_session.commit()

    response = api_client.get(f"/api/v1/rca/incidents/{incident_id}/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == incident_id
    assert body["investigation_job_id"] == "rca-api-job"
    assert body["evidence_quality"] == 84
    assert body["result"]["status"] == "confident"
    assert body["result"]["primary_hypothesis"]["title"] == "Deployment regression"


def test_get_latest_rca_returns_404_when_unavailable(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/rca/incidents/999/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "RCA for incident 999 not found"
