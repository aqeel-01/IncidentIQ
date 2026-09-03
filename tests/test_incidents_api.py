"""Tests for incident service and API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import IncidentStatus, Project, Service, Severity
from app.db.models.enums import ProjectRole
from app.db.session import get_db
from app.domain.incidents import (
    CreateIncidentInput,
    IncidentListFilters,
    IncidentService,
)
from app.main import create_app
from tests.auth_support import create_principal, grant_role, install_current_user


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, minutes, tzinfo=UTC)


@pytest.fixture
def incident_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
    )


@pytest_asyncio.fixture
async def db_session(
    incident_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        incident_settings.database_url,
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
    incident_settings: Settings,
    db_session: AsyncSession,
    principal,
) -> Iterator[TestClient]:
    app = create_app(settings=incident_settings)
    app.dependency_overrides[get_settings] = lambda: incident_settings

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
async def seeded_project(
    db_session: AsyncSession,
    principal,
) -> tuple[Project, Service]:
    project = Project(
        name="Payments",
        slug="payments",
        organization_id=principal.organization_id,
    )
    service = Service(name="payments-api", project=project)
    db_session.add(project)
    await db_session.flush()
    await grant_role(db_session, principal, project, ProjectRole.ADMIN)
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(service)
    return project, service


def test_create_incident_returns_201(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, service = seeded_project
    response = api_client.post(
        "/api/v1/incidents",
        json={
            "project_id": project.id,
            "service_id": service.id,
            "title": "Elevated 500 errors",
            "environment": "production",
            "severity": Severity.HIGH,
            "started_at": _ts().isoformat(),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["project_id"] == project.id
    assert body["service_id"] == service.id
    assert body["title"] == "Elevated 500 errors"
    assert body["environment"] == "production"
    assert body["severity"] == Severity.HIGH
    assert body["status"] == IncidentStatus.OPEN
    assert body["occurrence_count"] == 1
    assert body["action"] == "CREATED"
    assert body["deduplicated"] is False
    assert len(body["fingerprint"]) == 64


def test_create_incident_unknown_project_returns_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/incidents",
        json={
            "project_id": 9999,
            "title": "Missing project",
            "environment": "production",
            "severity": Severity.MEDIUM,
        },
    )
    assert response.status_code == 404


def test_create_incident_invalid_service_returns_400(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, _service = seeded_project
    response = api_client.post(
        "/api/v1/incidents",
        json={
            "project_id": project.id,
            "service_id": 9999,
            "title": "Bad service",
            "environment": "production",
            "severity": Severity.MEDIUM,
        },
    )
    assert response.status_code == 400


def test_list_incidents_supports_pagination(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, service = seeded_project
    for index, title in enumerate(("Alpha outage", "Beta outage", "Gamma outage")):
        response = api_client.post(
            "/api/v1/incidents",
            json={
                "project_id": project.id,
                "service_id": service.id,
                "title": title,
                "environment": "production",
                "severity": Severity.HIGH,
                "started_at": _ts(index).isoformat(),
            },
        )
        assert response.status_code == 201

    response = api_client.get(
        "/api/v1/incidents",
        params={"project_id": project.id, "page": 1, "page_size": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_list_incidents_filters_by_severity_and_status(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, service = seeded_project

    critical = api_client.post(
        "/api/v1/incidents",
        json={
            "project_id": project.id,
            "service_id": service.id,
            "title": "Critical open",
            "environment": "production",
            "severity": Severity.CRITICAL,
            "status": IncidentStatus.OPEN,
            "started_at": _ts(0).isoformat(),
        },
    )
    assert critical.status_code == 201

    resolved = api_client.post(
        "/api/v1/incidents",
        json={
            "project_id": project.id,
            "service_id": service.id,
            "title": "High resolved",
            "environment": "production",
            "severity": Severity.HIGH,
            "status": IncidentStatus.RESOLVED,
            "started_at": _ts(1).isoformat(),
        },
    )
    assert resolved.status_code == 201

    response = api_client.get(
        "/api/v1/incidents",
        params={
            "project_id": project.id,
            "severity": [Severity.CRITICAL],
            "status": [IncidentStatus.OPEN],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Critical open"


def test_incident_summary_reports_dashboard_counts(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, service = seeded_project
    now = datetime.now(UTC)
    incidents = [
        ("Critical open", Severity.CRITICAL, IncidentStatus.OPEN, now),
        (
            "Critical resolved",
            Severity.CRITICAL,
            IncidentStatus.RESOLVED,
            now - timedelta(days=3),
        ),
        ("High investigating", Severity.HIGH, IncidentStatus.INVESTIGATING, now),
        ("Low closed", Severity.LOW, IncidentStatus.CLOSED, now - timedelta(days=10)),
    ]
    for title, severity, incident_status, started_at in incidents:
        response = api_client.post(
            "/api/v1/incidents",
            json={
                "project_id": project.id,
                "service_id": service.id,
                "title": title,
                "environment": "production",
                "severity": severity,
                "status": incident_status,
                "started_at": started_at.isoformat(),
            },
        )
        assert response.status_code == 201

    response = api_client.get(
        "/api/v1/incidents/summary",
        params={"project_id": project.id, "recent_hours": 24},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["active"] == 2
    assert body["critical_active"] == 1
    assert body["recent"] == 2
    assert body["recent_window_hours"] == 24
    assert body["by_status"]["OPEN"] == 1
    assert body["by_status"]["RESOLVED"] == 1
    assert body["by_status"]["IDENTIFIED"] == 0
    assert body["by_severity"]["CRITICAL"] == 2
    assert body["by_severity"]["INFO"] == 0


def test_incident_summary_empty_project_returns_zero_counts(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, _service = seeded_project
    response = api_client.get(
        "/api/v1/incidents/summary",
        params={"project_id": project.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["active"] == 0
    assert body["critical_active"] == 0
    assert body["recent"] == 0


def test_get_incident_by_id(
    api_client: TestClient,
    seeded_project: tuple[Project, Service],
) -> None:
    project, service = seeded_project
    created = api_client.post(
        "/api/v1/incidents",
        json={
            "project_id": project.id,
            "service_id": service.id,
            "title": "Lookup me",
            "environment": "staging",
            "severity": Severity.LOW,
            "started_at": _ts().isoformat(),
        },
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    response = api_client.get(f"/api/v1/incidents/{incident_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Lookup me"


def test_get_incident_not_found_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/incidents/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_incident_service_list_filters(
    db_session: AsyncSession,
    seeded_project: tuple[Project, Service],
) -> None:
    project, service = seeded_project
    svc = IncidentService(db_session)
    await svc.create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="One",
            environment="production",
            severity=Severity.MEDIUM,
            status=IncidentStatus.INVESTIGATING,
            started_at=_ts(0),
        )
    )
    await svc.create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="Two",
            environment="production",
            severity=Severity.HIGH,
            status=IncidentStatus.OPEN,
            started_at=_ts(1),
        )
    )

    result = await svc.list(
        IncidentListFilters(
            project_id=project.id,
            severities=(Severity.HIGH,),
            statuses=(IncidentStatus.OPEN,),
        )
    )
    assert result.total == 1
    assert result.items[0].title == "Two"
