"""Tests for POST /api/v1/logs/upload."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import LogUpload, LogUploadStatus, Organization, Project
from app.db.session import get_db
from app.main import create_app


@pytest.fixture
def upload_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        log_upload_dir=str(tmp_path / "uploads"),
        log_upload_max_bytes=256,
        log_upload_chunk_bytes=64,
    )


@pytest_asyncio.fixture
async def db_session(
    upload_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        upload_settings.database_url,
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
def upload_client(
    upload_settings: Settings, db_session: AsyncSession
) -> Iterator[TestClient]:
    app = create_app(settings=upload_settings)
    app.dependency_overrides[get_settings] = lambda: upload_settings

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def project_id(db_session: AsyncSession) -> int:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project.id


def test_upload_valid_log_file(
    upload_client: TestClient,
    db_session: AsyncSession,
    project_id: int,
    upload_settings: Settings,
) -> None:
    content = b"2026-09-01 ERROR service down\n"
    response = upload_client.post(
        "/api/v1/logs/upload",
        data={"project_id": str(project_id)},
        files={"file": ("app.log", content, "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status"] == LogUploadStatus.QUEUED
    assert body["filename"] == "app.log"
    assert body["file_extension"] == ".log"
    assert body["file_size_bytes"] == len(content)
    assert body["project_id"] == project_id

    stored = (
        Path(upload_settings.log_upload_dir) / str(project_id) / f"{body['job_id']}.log"
    )
    assert stored.is_file()
    assert stored.read_bytes() == content


@pytest.mark.parametrize(
    "filename",
    ["report.json", "events.jsonl", "data.csv", "notes.txt"],
)
def test_upload_supported_extensions(
    upload_client: TestClient,
    project_id: int,
    filename: str,
) -> None:
    response = upload_client.post(
        "/api/v1/logs/upload",
        data={"project_id": str(project_id)},
        files={"file": (filename, b"{}", "application/octet-stream")},
    )
    assert response.status_code == 202
    assert response.json()["filename"] == filename


def test_upload_rejects_unsupported_extension(
    upload_client: TestClient,
    project_id: int,
) -> None:
    response = upload_client.post(
        "/api/v1/logs/upload",
        data={"project_id": str(project_id)},
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"]


def test_upload_sanitizes_path_traversal_filename(
    upload_client: TestClient,
    project_id: int,
) -> None:
    response = upload_client.post(
        "/api/v1/logs/upload",
        data={"project_id": str(project_id)},
        files={"file": ("../../etc/passwd.log", b"x", "text/plain")},
    )
    assert response.status_code == 202
    assert response.json()["filename"] == "passwd.log"


def test_upload_rejects_oversized_file(
    upload_client: TestClient,
    project_id: int,
    upload_settings: Settings,
) -> None:
    # max_bytes=256, chunk_bytes=64 — stream should abort before full read.
    oversized = b"x" * (upload_settings.log_upload_max_bytes + 1)
    response = upload_client.post(
        "/api/v1/logs/upload",
        data={"project_id": str(project_id)},
        files={"file": ("big.log", oversized, "text/plain")},
    )

    assert response.status_code == 413
    assert "maximum size" in response.json()["detail"]


def test_upload_unknown_project(upload_client: TestClient) -> None:
    response = upload_client.post(
        "/api/v1/logs/upload",
        data={"project_id": "9999"},
        files={"file": ("app.log", b"x", "text/plain")},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_persists_job_record(
    upload_client: TestClient,
    db_session: AsyncSession,
    project_id: int,
) -> None:
    response = upload_client.post(
        "/api/v1/logs/upload",
        data={"project_id": str(project_id)},
        files={"file": ("app.log", b"line", "text/plain")},
    )
    job_id = response.json()["job_id"]

    row = (
        await db_session.execute(select(LogUpload).where(LogUpload.id == job_id))
    ).scalar_one()
    assert row.status is LogUploadStatus.QUEUED
    assert row.original_filename == "app.log"
