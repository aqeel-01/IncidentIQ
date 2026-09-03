"""Tests for the incident timeline API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import Organization, Severity
from app.db.models.enums import ProjectRole
from app.db.session import get_db
from app.domain.events import (
    AlertEvent,
    AlertStatus,
    DeploymentEvent,
    LogEvent,
    MetricEvent,
)
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.ingestion import EventIngestionService
from app.main import create_app
from tests.auth_support import create_principal, grant_role, install_current_user
from tests.test_timeline_service import _base_event_fields, _seed_project, _ts


@pytest.fixture
def timeline_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
    )


@pytest_asyncio.fixture
async def db_session(
    timeline_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        timeline_settings.database_url,
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
    timeline_settings: Settings,
    db_session: AsyncSession,
    principal,
) -> Iterator[TestClient]:
    app = create_app(settings=timeline_settings)
    app.dependency_overrides[get_settings] = lambda: timeline_settings

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
async def test_get_timeline_returns_chronological_payload(
    api_client: TestClient,
    db_session: AsyncSession,
    principal,
) -> None:
    org = await db_session.get(Organization, principal.organization_id)
    project, service = await _seed_project(db_session, organization=org)
    await grant_role(db_session, principal, project, ProjectRole.ADMIN)
    ingestion = EventIngestionService(db_session)

    await ingestion.ingest_batch(
        project.id,
        [
            DeploymentEvent(
                timestamp=_ts(-30),
                version="v1.0.0",
                commit_sha="abc",
                repository="payments-api",
                service="payments-api",
                **_base_event_fields(),
            ),
            MetricEvent(
                timestamp=_ts(-5),
                metric_name="latency_ms",
                value=900.0,
                service="payments-api",
                **_base_event_fields(),
            ),
            LogEvent(
                timestamp=_ts(0),
                message="checkout failed",
                severity=Severity.CRITICAL,
                service="payments-api",
                **_base_event_fields(),
            ),
            AlertEvent(
                timestamp=_ts(5),
                name="CheckoutFailures",
                status=AlertStatus.FIRING,
                severity=Severity.CRITICAL,
                service="payments-api",
                **_base_event_fields(),
            ),
        ],
    )

    incident = (
        await IncidentService(db_session).create(
            CreateIncidentInput(
                project_id=project.id,
                service_id=service.id,
                title="Checkout failures",
                environment="production",
                severity=Severity.CRITICAL,
                started_at=_ts(0),
            )
        )
    ).incident
    await db_session.commit()

    response = api_client.get(f"/api/v1/timeline/{incident.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == incident.id
    assert body["project_id"] == project.id
    assert len(body["entries"]) == 4

    entry_times = [
        datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        for entry in body["entries"]
    ]
    assert entry_times == sorted(entry_times)

    markers = body["markers"]
    assert markers["first_anomaly"]["category"] == "metric"
    assert markers["first_relevant_error"]["category"] == "log"
    assert markers["first_alert"]["title"] == "CheckoutFailures"
    assert markers["recent_deployment"]["title"] == "v1.0.0 abc"
    assert markers["recovery"] is None
    assert "correlations" in body
    assert len(body["correlations"]) >= 2
    kinds = {item["kind"] for item in body["correlations"]}
    assert "deployment_to_error" in kinds
    assert "error_to_alert" in kinds
    assert body["deployment_correlation"] is not None
    assert body["deployment_correlation"]["is_related"] is True
    assert body["deployment_correlation"]["supporting_evidence"]
    assert body["service_correlation"] is not None
    assert body["service_correlation"]["services"]


def test_get_timeline_returns_404_for_missing_incident(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/timeline/999")
    assert response.status_code == 404
