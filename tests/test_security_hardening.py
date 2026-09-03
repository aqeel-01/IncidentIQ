"""Security hardening tests: redaction, uploads, rate limits, bootstrap."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.middleware import reset_rate_limiter
from app.core.config import Settings, get_settings
from app.core.logging import JsonFormatter, reset_logging_for_tests
from app.core.security import (
    redact_dsn,
    sanitize_error_message,
    secrets_from_settings,
)
from app.db.base import Base
from app.db.session import get_db
from app.domain.uploads import (
    UploadValidationError,
    resolve_upload_destination,
    validate_upload_content_type,
)
from app.main import create_app
from tests.auth_support import TEST_PASSWORD, create_principal, install_current_user


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


def test_sanitize_error_message_redacts_bearer_and_dsn() -> None:
    message = (
        "failed Authorization: Bearer super-secret-token "
        "url=postgresql://incidentiq:dbpass@localhost:5432/incidentiq "
        "api_key=abc123 password=hunter2 "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaa.bbb"
    )
    sanitized = sanitize_error_message(message, secrets=("abc123",))
    assert "super-secret-token" not in sanitized
    assert "dbpass" not in sanitized
    assert "hunter2" not in sanitized
    assert "abc123" not in sanitized
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaa.bbb" not in sanitized
    assert "***" in sanitized


def test_redact_dsn_removes_password() -> None:
    assert (
        redact_dsn("postgresql://user:s3cret@db.example:5432/app")
        == "postgresql://user:***@db.example:5432/app"
    )


def test_json_formatter_redacts_secrets_from_log_records() -> None:
    reset_logging_for_tests()
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Authorization: Bearer leaked-token password=visible",
        args=(),
        exc_info=None,
    )
    rendered = formatter.format(record)
    assert "leaked-token" not in rendered
    assert "visible" not in rendered
    assert "***" in rendered


def test_validate_upload_content_type_rejects_unexpected_media() -> None:
    with pytest.raises(UploadValidationError, match="unsupported content type"):
        validate_upload_content_type("text/html")


def test_resolve_upload_destination_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(UploadValidationError, match="invalid stored filename"):
        resolve_upload_destination(tmp_path, 1, "../outside.log")
    destination = resolve_upload_destination(tmp_path, 1, "safe.log")
    assert destination.parent == (tmp_path / "1").resolve()
    assert destination.name == "safe.log"


@pytest.fixture
def security_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        jwt_secret_key="test-jwt-secret-key-not-for-prod",
        auth_bootstrap_disabled=False,
        auth_login_rate_limit=3,
        auth_bootstrap_rate_limit=2,
        auth_rate_limit_window_seconds=60,
        upload_rate_limit=2,
        upload_rate_limit_window_seconds=60,
        log_upload_dir=str(tmp_path / "uploads"),
        log_upload_max_bytes=1024,
        log_upload_chunk_bytes=64,
    )


@pytest_asyncio.fixture
async def db_session(security_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        security_settings.database_url,
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
    security_settings: Settings,
    db_session: AsyncSession,
) -> Iterator[TestClient]:
    app = create_app(settings=security_settings)
    app.dependency_overrides[get_settings] = lambda: security_settings

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_login_rate_limit_returns_429(api_client: TestClient) -> None:
    payload = {"email": "nobody@acme.test", "password": TEST_PASSWORD}
    for _ in range(3):
        response = api_client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401
    limited = api_client.post("/api/v1/auth/login", json=payload)
    assert limited.status_code == 429
    assert "rate limit" in limited.json()["detail"]


def test_bootstrap_rate_limit_returns_429(api_client: TestClient) -> None:
    payload = {
        "organization_name": "Acme",
        "organization_slug": "acme",
        "project_name": "Payments",
        "project_slug": "payments",
        "email": "admin@acme.test",
        "password": TEST_PASSWORD,
    }
    first = api_client.post("/api/v1/auth/bootstrap", json=payload)
    assert first.status_code == 201
    second = api_client.post(
        "/api/v1/auth/bootstrap",
        json={**payload, "organization_slug": "acme-2", "email": "admin2@acme.test"},
    )
    assert second.status_code == 400
    third = api_client.post(
        "/api/v1/auth/bootstrap",
        json={**payload, "organization_slug": "acme-3", "email": "admin3@acme.test"},
    )
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_bootstrap_disabled_in_production(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        jwt_secret_key="prod-jwt-secret-key-value",
        connector_secret_key="",
        auth_bootstrap_disabled=None,
        log_upload_dir=str(tmp_path / "uploads"),
    )
    assert settings.resolved_auth_bootstrap_disabled is True

    engine = create_async_engine(
        "sqlite+aiosqlite://",
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
        app = create_app(settings=settings)
        app.dependency_overrides[get_settings] = lambda: settings

        async def _override_db() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_db] = _override_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/auth/bootstrap",
                    json={
                        "organization_name": "Acme",
                        "organization_slug": "acme",
                        "project_name": "Payments",
                        "project_slug": "payments",
                        "email": "admin@acme.test",
                        "password": TEST_PASSWORD,
                    },
                )
            assert response.status_code == 400
            assert "disabled" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    await engine.dispose()


@pytest.mark.asyncio
async def test_upload_rejects_disallowed_content_type(
    security_settings: Settings,
    db_session: AsyncSession,
) -> None:
    principal = await create_principal(db_session)
    from app.db.models import Project
    from app.db.models.enums import ProjectRole
    from tests.auth_support import grant_role

    project = Project(
        name="Payments",
        slug="payments",
        organization_id=principal.organization_id,
    )
    db_session.add(project)
    await db_session.flush()
    await grant_role(db_session, principal, project, ProjectRole.ADMIN)
    await db_session.commit()

    app = create_app(settings=security_settings)
    app.dependency_overrides[get_settings] = lambda: security_settings

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    install_current_user(app, principal)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/logs/upload",
            data={"project_id": str(project.id)},
            files={"file": ("evil.log", b"<html>", "text/html")},
        )
    app.dependency_overrides.clear()
    assert response.status_code == 400
    assert "unsupported content type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_rate_limit_returns_429(
    security_settings: Settings,
    db_session: AsyncSession,
) -> None:
    principal = await create_principal(db_session)
    from app.db.models import Project
    from app.db.models.enums import ProjectRole
    from tests.auth_support import grant_role

    project = Project(
        name="Payments",
        slug="payments",
        organization_id=principal.organization_id,
    )
    db_session.add(project)
    await db_session.flush()
    await grant_role(db_session, principal, project, ProjectRole.ADMIN)
    await db_session.commit()

    app = create_app(settings=security_settings)
    app.dependency_overrides[get_settings] = lambda: security_settings

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    install_current_user(app, principal)

    with TestClient(app) as client:
        for _ in range(2):
            ok = client.post(
                "/api/v1/logs/upload",
                data={"project_id": str(project.id)},
                files={"file": ("app.log", b"ok", "text/plain")},
            )
            assert ok.status_code == 202
        limited = client.post(
            "/api/v1/logs/upload",
            data={"project_id": str(project.id)},
            files={"file": ("app.log", b"ok", "text/plain")},
        )
    app.dependency_overrides.clear()
    assert limited.status_code == 429


def test_secrets_from_settings_excludes_blank_values() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        groq_api_key="gsk_test",
        jwt_secret_key="",
        connector_secret_key=" ",
    )
    assert secrets_from_settings(settings) == ("gsk_test",)


def test_connector_create_rejects_oversized_credential_map(
    api_client: TestClient,
) -> None:
    # Unauthenticated create should 401 before validation body size matters,
    # so bootstrap an admin and call authenticated endpoint via override path
    # in a dedicated fixture is heavier. Validate schema-level rejection:
    from pydantic import ValidationError

    from app.api.routes.connectors import CreateConnectorRequest
    from app.connectors.types import ConnectorType

    with pytest.raises(ValidationError):
        CreateConnectorRequest(
            project_id=1,
            name="too-big",
            connector_type=ConnectorType.PROMETHEUS,
            settings={},
            credentials={f"k{i}": "v" for i in range(50)},
        )
