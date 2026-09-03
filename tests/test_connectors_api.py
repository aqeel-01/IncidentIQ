"""Tests for connector management API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.connectors import (
    ConnectionTestResult,
    Connector,
    ConnectorState,
    ConnectorType,
)
from app.connectors.types import HealthCheckResult
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import Project
from app.db.models.enums import ProjectRole
from app.db.session import get_db
from app.domain.connectors.service import ConnectorManagementService
from app.main import create_app
from tests.auth_support import create_principal, grant_role, install_current_user


class RecordingConnector(Connector):
    def __init__(self, config, *, success: bool = True) -> None:
        super().__init__(config)
        self.success = success
        self.test_calls = 0

    async def connect(self) -> None:
        self._state = ConnectorState.CONNECTED

    async def disconnect(self) -> None:
        self._state = ConnectorState.DISCONNECTED

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            connector_type=self.connector_type,
            name=self.name,
            healthy=True,
            state=self.state,
            detail="ok",
        )

    async def test_connection(self) -> ConnectionTestResult:
        self.test_calls += 1
        return ConnectionTestResult(
            connector_type=self.connector_type,
            name=self.name,
            success=self.success,
            detail="probe ok" if self.success else "probe failed",
            tested_at=datetime.now(UTC),
        )


@pytest.fixture
def connector_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        connector_secret_key="",
    )


@pytest_asyncio.fixture
async def db_session(
    connector_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        connector_settings.database_url,
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
    connector_settings: Settings,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    principal,
) -> Iterator[TestClient]:
    app = create_app(settings=connector_settings)
    app.dependency_overrides[get_settings] = lambda: connector_settings

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    install_current_user(app, principal)

    def _factory(config):
        return RecordingConnector(config, success=True)

    monkeypatch.setattr(
        "app.domain.connectors.service.default_connector_registry",
        lambda: _FakeRegistry(_factory),
    )

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


class _FakeRegistry:
    def __init__(self, factory) -> None:
        self._factory = factory

    def create(self, config):
        return self._factory(config)

    def is_registered(self, connector_type: ConnectorType) -> bool:
        return True

    def supported_types(self) -> frozenset[ConnectorType]:
        return frozenset(ConnectorType)


@pytest_asyncio.fixture
async def principal(db_session: AsyncSession):
    return await create_principal(db_session)


@pytest_asyncio.fixture
async def seeded_project(db_session: AsyncSession, principal) -> Project:
    project = Project(
        name="Payments",
        slug="payments",
        organization_id=principal.organization_id,
    )
    db_session.add(project)
    await db_session.flush()
    await grant_role(db_session, principal, project, ProjectRole.ADMIN)
    await db_session.commit()
    await db_session.refresh(project)
    return project


def test_list_connector_types(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/connectors/types")
    assert response.status_code == 200
    body = response.json()
    types = {item["connector_type"] for item in body["items"]}
    assert ConnectorType.PROMETHEUS in types
    prometheus = next(
        item for item in body["items"] if item["connector_type"] == "prometheus"
    )
    assert "bearer_token" in prometheus["secret_fields"]
    assert "password" in prometheus["secret_fields"]
    assert "base_url" in prometheus["setting_fields"]


def test_create_connector_never_returns_credentials(
    api_client: TestClient,
    seeded_project: Project,
) -> None:
    response = api_client.post(
        "/api/v1/connectors",
        json={
            "project_id": seeded_project.id,
            "name": "prod-prometheus",
            "connector_type": "prometheus",
            "settings": {
                "base_url": "https://prometheus.example.com",
                "timeout_seconds": 8,
                "verify_tls": True,
            },
            "credentials": {"bearer_token": "super-secret-token"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "prod-prometheus"
    assert body["enabled"] is True
    assert body["settings"]["base_url"] == "https://prometheus.example.com"
    assert body["configured_credentials"] == ["bearer_token"]
    dumped = response.text
    assert "super-secret-token" not in dumped
    assert "bearer_token" not in body["settings"]


def test_update_keeps_existing_credentials_when_omitted(
    api_client: TestClient,
    seeded_project: Project,
) -> None:
    created = api_client.post(
        "/api/v1/connectors",
        json={
            "project_id": seeded_project.id,
            "name": "github-main",
            "connector_type": "github",
            "settings": {"owner": "acme", "repository": "payments"},
            "credentials": {"token": "ghp_secret"},
        },
    )
    assert created.status_code == 201
    connector_id = created.json()["id"]

    updated = api_client.patch(
        f"/api/v1/connectors/{connector_id}",
        json={"settings": {"owner": "acme", "repository": "payments-api"}},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["settings"]["repository"] == "payments-api"
    assert body["configured_credentials"] == ["token"]
    assert "ghp_secret" not in updated.text


def test_enable_disable_and_delete(
    api_client: TestClient,
    seeded_project: Project,
) -> None:
    created = api_client.post(
        "/api/v1/connectors",
        json={
            "project_id": seeded_project.id,
            "name": "azure",
            "connector_type": "azure_devops",
            "settings": {"organization": "acme"},
            "credentials": {"personal_access_token": "ado-secret"},
        },
    )
    connector_id = created.json()["id"]

    disabled = api_client.post(f"/api/v1/connectors/{connector_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = api_client.post(f"/api/v1/connectors/{connector_id}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    deleted = api_client.delete(f"/api/v1/connectors/{connector_id}")
    assert deleted.status_code == 204

    missing = api_client.get(f"/api/v1/connectors/{connector_id}")
    assert missing.status_code == 404


def test_test_connection_persists_result_without_leaking_secrets(
    api_client: TestClient,
    seeded_project: Project,
) -> None:
    created = api_client.post(
        "/api/v1/connectors",
        json={
            "project_id": seeded_project.id,
            "name": "db-logs",
            "connector_type": "database",
            "settings": {
                "dialect": "postgresql",
                "table": "app_logs",
            },
            "credentials": {
                "connection_url": "postgresql://user:secret@localhost/db",
            },
        },
    )
    assert created.status_code == 201
    connector_id = created.json()["id"]

    tested = api_client.post(f"/api/v1/connectors/{connector_id}/test")
    assert tested.status_code == 200
    body = tested.json()
    assert body["success"] is True
    assert body["detail"] == "probe ok"
    assert body["connector"]["last_test_success"] is True
    assert "secret" not in tested.text
    assert body["connector"]["configured_credentials"] == ["connection_url"]


def test_list_connectors_for_project(
    api_client: TestClient,
    seeded_project: Project,
) -> None:
    api_client.post(
        "/api/v1/connectors",
        json={
            "project_id": seeded_project.id,
            "name": "a-prom",
            "connector_type": "prometheus",
            "settings": {"base_url": "https://a.example.com"},
            "credentials": {},
        },
    )
    api_client.post(
        "/api/v1/connectors",
        json={
            "project_id": seeded_project.id,
            "name": "b-prom",
            "connector_type": "prometheus",
            "settings": {"base_url": "https://b.example.com"},
            "credentials": {},
        },
    )

    response = api_client.get(
        "/api/v1/connectors",
        params={"project_id": seeded_project.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["name"] for item in body["items"]] == ["a-prom", "b-prom"]


@pytest.mark.asyncio
async def test_service_rejects_duplicate_names(
    db_session: AsyncSession,
    connector_settings: Settings,
    seeded_project: Project,
) -> None:
    service = ConnectorManagementService(db_session, settings=connector_settings)
    await service.create(
        project_id=seeded_project.id,
        name="dup",
        connector_type=ConnectorType.PROMETHEUS,
        settings={"base_url": "https://example.com"},
        credentials={},
    )
    with pytest.raises(Exception, match="already exists"):
        await service.create(
            project_id=seeded_project.id,
            name="dup",
            connector_type=ConnectorType.PROMETHEUS,
            settings={"base_url": "https://example.com"},
            credentials={},
        )
