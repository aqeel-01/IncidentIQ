"""Authentication, RBAC, and cross-project isolation tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import Organization, Project, ProjectRole, Service, Severity, User
from app.db.session import get_db
from app.domain.auth.passwords import hash_password
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.main import create_app
from tests.auth_support import TEST_PASSWORD, create_user

PASSWORD = TEST_PASSWORD


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        jwt_secret_key="test-jwt-secret-key-not-for-prod",
    )


@pytest_asyncio.fixture
async def db_session(auth_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        auth_settings.database_url,
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
    auth_settings: Settings,
    db_session: AsyncSession,
) -> Iterator[TestClient]:
    app = create_app(settings=auth_settings)
    app.dependency_overrides[get_settings] = lambda: auth_settings

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


def _bootstrap(client: TestClient, **overrides):
    payload = {
        "organization_name": "Acme",
        "organization_slug": "acme",
        "project_name": "Payments",
        "project_slug": "payments",
        "email": "admin@acme.test",
        "password": PASSWORD,
        "full_name": "Ada Admin",
        **overrides,
    }
    return client.post("/api/v1/auth/bootstrap", json=payload)


def test_health_remains_unauthenticated(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200


def test_protected_route_without_token_returns_401(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/incidents", params={"project_id": 1})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_invalid_token_returns_401(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/incidents",
        params={"project_id": 1},
        headers=_auth_header("not-a-real-token"),
    )
    assert response.status_code == 401


def test_bootstrap_creates_admin_and_login_works(api_client: TestClient) -> None:
    created = _bootstrap(api_client)
    assert created.status_code == 201
    body = created.json()
    assert body["user"]["email"] == "admin@acme.test"
    assert body["user"]["memberships"][0]["role"] == "ADMIN"
    assert "password" not in str(body).lower() or "hashed_password" not in str(body)

    second = _bootstrap(api_client)
    assert second.status_code == 400

    login = _login(api_client, "admin@acme.test")
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = api_client.get("/api/v1/auth/me", headers=_auth_header(token))
    assert me.status_code == 200
    assert me.json()["email"] == "admin@acme.test"
    assert me.json()["memberships"][0]["project_id"] == body["project_id"]


def test_login_rejects_bad_password(api_client: TestClient) -> None:
    _bootstrap(api_client)
    response = _login(api_client, "admin@acme.test", "wrong-password")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cross_project_isolation(
    api_client: TestClient,
    db_session: AsyncSession,
) -> None:
    org_a = Organization(name="Acme", slug="acme")
    org_b = Organization(name="Beta", slug="beta")
    project_a = Project(name="Payments", slug="payments", organization=org_a)
    project_b = Project(name="Billing", slug="billing", organization=org_b)
    db_session.add_all([project_a, project_b])
    await db_session.flush()

    user_a = await create_user(
        db_session,
        org_a,
        email="a@acme.test",
        role=ProjectRole.ADMIN,
        project=project_a,
    )
    user_b = await create_user(
        db_session,
        org_b,
        email="b@beta.test",
        role=ProjectRole.ADMIN,
        project=project_b,
    )
    await db_session.commit()

    token_a = _login(api_client, user_a.email).json()["access_token"]
    token_b = _login(api_client, user_b.email).json()["access_token"]

    visible = api_client.get(
        "/api/v1/incidents",
        params={"project_id": project_a.id},
        headers=_auth_header(token_a),
    )
    assert visible.status_code == 200

    blocked = api_client.get(
        "/api/v1/incidents",
        params={"project_id": project_b.id},
        headers=_auth_header(token_a),
    )
    assert blocked.status_code == 403

    other_way = api_client.get(
        "/api/v1/incidents",
        params={"project_id": project_a.id},
        headers=_auth_header(token_b),
    )
    assert other_way.status_code == 403


@pytest.mark.asyncio
async def test_incident_detail_is_isolated_across_projects(
    api_client: TestClient,
    db_session: AsyncSession,
) -> None:
    org_a = Organization(name="Acme", slug="acme")
    org_b = Organization(name="Beta", slug="beta")
    project_a = Project(name="Payments", slug="payments", organization=org_a)
    project_b = Project(name="Billing", slug="billing", organization=org_b)
    db_session.add_all([project_a, project_b])
    await db_session.flush()

    user_a = await create_user(
        db_session,
        org_a,
        email="a@acme.test",
        role=ProjectRole.VIEWER,
        project=project_a,
    )
    await create_user(
        db_session,
        org_b,
        email="b@beta.test",
        role=ProjectRole.ADMIN,
        project=project_b,
    )
    created = await IncidentService(db_session).create(
        CreateIncidentInput(
            project_id=project_b.id,
            title="Secret outage",
            environment="production",
            severity=Severity.HIGH,
            started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()

    token_a = _login(api_client, user_a.email).json()["access_token"]
    response = api_client.get(
        f"/api/v1/incidents/{created.incident.id}",
        headers=_auth_header(token_a),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_create_incident(
    api_client: TestClient,
    db_session: AsyncSession,
) -> None:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    db_session.add(project)
    await db_session.flush()
    viewer = await create_user(
        db_session,
        org,
        email="viewer@acme.test",
        role=ProjectRole.VIEWER,
        project=project,
    )
    await db_session.commit()

    token = _login(api_client, viewer.email).json()["access_token"]
    response = api_client.post(
        "/api/v1/incidents",
        headers=_auth_header(token),
        json={
            "project_id": project.id,
            "service_id": service.id,
            "title": "Should fail",
            "environment": "production",
            "severity": Severity.HIGH,
            "started_at": datetime(2026, 9, 1, 12, 0, tzinfo=UTC).isoformat(),
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_engineer_can_create_incident_but_not_manage_connectors(
    api_client: TestClient,
    db_session: AsyncSession,
) -> None:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    db_session.add(project)
    await db_session.flush()
    engineer = await create_user(
        db_session,
        org,
        email="eng@acme.test",
        role=ProjectRole.ENGINEER,
        project=project,
    )
    await db_session.commit()

    token = _login(api_client, engineer.email).json()["access_token"]
    headers = _auth_header(token)

    created = api_client.post(
        "/api/v1/incidents",
        headers=headers,
        json={
            "project_id": project.id,
            "service_id": service.id,
            "title": "Elevated errors",
            "environment": "production",
            "severity": Severity.HIGH,
            "started_at": datetime(2026, 9, 1, 12, 0, tzinfo=UTC).isoformat(),
        },
    )
    assert created.status_code == 201

    listed = api_client.get(
        "/api/v1/connectors",
        params={"project_id": project.id},
        headers=headers,
    )
    assert listed.status_code == 200

    connector = api_client.post(
        "/api/v1/connectors",
        headers=headers,
        json={
            "project_id": project.id,
            "name": "Prom",
            "connector_type": "prometheus",
            "settings": {"base_url": "http://prometheus.local"},
        },
    )
    assert connector.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_assign_roles_and_user_without_membership_is_denied(
    api_client: TestClient,
    db_session: AsyncSession,
) -> None:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    db_session.add(project)
    await db_session.flush()
    admin = await create_user(
        db_session,
        org,
        email="admin@acme.test",
        role=ProjectRole.ADMIN,
        project=project,
    )
    outsider = User(
        organization_id=org.id,
        email="none@acme.test",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
    )
    db_session.add(outsider)
    await db_session.commit()
    await db_session.refresh(outsider)

    admin_token = _login(api_client, admin.email).json()["access_token"]
    outsider_token = _login(api_client, outsider.email).json()["access_token"]

    denied = api_client.get(
        "/api/v1/incidents",
        params={"project_id": project.id},
        headers=_auth_header(outsider_token),
    )
    assert denied.status_code == 403

    assigned = api_client.put(
        f"/api/v1/projects/{project.id}/memberships",
        headers=_auth_header(admin_token),
        json={"user_id": outsider.id, "role": "VIEWER"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["role"] == "VIEWER"

    allowed = api_client.get(
        "/api/v1/incidents",
        params={"project_id": project.id},
        headers=_auth_header(outsider_token),
    )
    assert allowed.status_code == 200


def test_same_org_second_project_is_isolated_until_granted(
    api_client: TestClient,
) -> None:
    first = _bootstrap(api_client)
    admin_token = first.json()["access_token"]
    admin_headers = _auth_header(admin_token)
    first_project_id = first.json()["project_id"]

    created_user = api_client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "eng@acme.test",
            "password": PASSWORD,
            "full_name": "Eng",
        },
    )
    assert created_user.status_code == 201
    engineer_id = created_user.json()["id"]

    second = api_client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "Billing", "slug": "billing"},
    )
    assert second.status_code == 201
    billing_id = second.json()["id"]
    assert billing_id != first_project_id

    api_client.put(
        f"/api/v1/projects/{first_project_id}/memberships",
        headers=admin_headers,
        json={"user_id": engineer_id, "role": "ENGINEER"},
    )

    eng_token = _login(api_client, "eng@acme.test").json()["access_token"]
    can_see_payments = api_client.get(
        "/api/v1/incidents",
        params={"project_id": first_project_id},
        headers=_auth_header(eng_token),
    )
    assert can_see_payments.status_code == 200

    cannot_see_billing = api_client.get(
        "/api/v1/incidents",
        params={"project_id": billing_id},
        headers=_auth_header(eng_token),
    )
    assert cannot_see_billing.status_code == 403
