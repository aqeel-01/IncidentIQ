"""End-to-end tests for the Alertmanager Prometheus webhook."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import (
    Incident,
    IncidentStatus,
    Organization,
    Project,
    Service,
    Severity,
)
from app.db.session import get_db
from app.domain.alertmanager import (
    AlertmanagerWebhookPayload,
    parse_alertmanager_webhook,
)
from app.domain.events import AlertStatus
from app.main import create_app


def _ts() -> str:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _firing_payload(**label_overrides: str) -> dict:
    labels = {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "job": "payments-api",
        "environment": "production",
        "instance": "10.0.0.1:8080",
    }
    labels.update(label_overrides)
    return {
        "receiver": "incidentiq",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": labels,
                "annotations": {
                    "summary": "High error rate on payments-api",
                    "description": "Error rate exceeded threshold",
                },
                "startsAt": _ts(),
                "endsAt": "0001-01-01T00:00:00Z",
                "fingerprint": "fp-123",
            }
        ],
    }


def _resolved_payload(fingerprint: str = "fp-123") -> dict:
    return {
        "receiver": "incidentiq",
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "HighErrorRate",
                    "severity": "critical",
                    "job": "payments-api",
                    "environment": "production",
                },
                "annotations": {"summary": "High error rate on payments-api"},
                "startsAt": _ts(),
                "endsAt": datetime(2026, 9, 1, 12, 30, tzinfo=UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "fingerprint": fingerprint,
            }
        ],
    }


@pytest.fixture
def alert_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
    )


@pytest_asyncio.fixture
async def db_session(alert_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        alert_settings.database_url,
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
    alert_settings: Settings, db_session: AsyncSession
) -> Iterator[TestClient]:
    app = create_app(settings=alert_settings)
    app.dependency_overrides[get_settings] = lambda: alert_settings

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_project(
    db_session: AsyncSession,
) -> tuple[Project, Service]:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(service)
    return project, service


def test_parse_alertmanager_webhook_builds_alert_events() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(_firing_payload())
    events = parse_alertmanager_webhook(payload)

    assert len(events) == 1
    event = events[0]
    assert event.name == "HighErrorRate"
    assert event.status is AlertStatus.FIRING
    assert event.severity is Severity.CRITICAL
    assert event.service == "payments-api"
    assert event.environment == "production"
    assert event.source == "alertmanager:incidentiq"
    assert event.source_type == "alertmanager"
    assert event.raw_data["fingerprint"] == "fp-123"


def test_webhook_rejects_payload_without_alerts(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": 1},
        json={"receiver": "incidentiq", "status": "firing", "alerts": []},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_creates_incident_for_firing_alert(
    api_client: TestClient,
    db_session: AsyncSession,
    seeded_project: tuple[Project, Service],
) -> None:
    project, service = seeded_project
    response = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": project.id},
        json=_firing_payload(),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["alerts_received"] == 1
    assert body["incidents_created"] == 1
    assert body["incidents_merged"] == 0
    assert body["outcomes"][0]["action"] == "CREATED"
    assert body["outcomes"][0]["incident_id"] is not None

    incident_id = body["outcomes"][0]["incident_id"]
    incident = (
        await db_session.execute(select(Incident).where(Incident.id == incident_id))
    ).scalar_one()
    assert incident.title == "HighErrorRate"
    assert incident.severity is Severity.CRITICAL
    assert incident.status is IncidentStatus.OPEN
    assert incident.service_id == service.id
    assert incident.occurrence_count == 1


@pytest.mark.asyncio
async def test_duplicate_firing_alerts_merge_into_one_incident(
    api_client: TestClient,
    db_session: AsyncSession,
    seeded_project: tuple[Project, Service],
) -> None:
    project, _service = seeded_project

    first = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": project.id},
        json=_firing_payload(instance="10.0.0.1:8080"),
    )
    second = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": project.id},
        json=_firing_payload(instance="10.0.0.2:8080"),
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["incidents_created"] == 1
    assert second.json()["incidents_merged"] == 1
    assert (
        first.json()["outcomes"][0]["incident_id"]
        == second.json()["outcomes"][0]["incident_id"]
    )

    count = (
        await db_session.execute(select(func.count()).select_from(Incident))
    ).scalar_one()
    assert count == 1

    incident = await db_session.get(
        Incident, first.json()["outcomes"][0]["incident_id"]
    )
    assert incident is not None
    assert incident.occurrence_count == 2


@pytest.mark.asyncio
async def test_resolved_alert_updates_matching_incident(
    api_client: TestClient,
    db_session: AsyncSession,
    seeded_project: tuple[Project, Service],
) -> None:
    project, _service = seeded_project

    firing = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": project.id},
        json=_firing_payload(),
    )
    incident_id = firing.json()["outcomes"][0]["incident_id"]

    resolved = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": project.id},
        json=_resolved_payload(),
    )

    assert resolved.status_code == 202
    body = resolved.json()
    assert body["incidents_resolved"] == 1
    assert body["outcomes"][0]["action"] == "RESOLVED"
    assert body["outcomes"][0]["incident_id"] == incident_id

    incident = await db_session.get(Incident, incident_id)
    assert incident is not None
    assert incident.status is IncidentStatus.RESOLVED
    assert incident.ended_at is not None


def test_webhook_unknown_project_returns_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": 9999},
        json=_firing_payload(),
    )
    assert response.status_code == 404


def test_webhook_rejects_alert_without_alertname(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, _service = seeded_project
    payload = _firing_payload()
    del payload["alerts"][0]["labels"]["alertname"]

    response = api_client.post(
        "/api/v1/alerts/prometheus",
        params={"project_id": project.id},
        json=payload,
    )
    assert response.status_code == 400
    assert "alertname" in response.json()["detail"]
