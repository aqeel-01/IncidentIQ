"""Integration tests for event ingestion persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Event, Organization, Project, Service, Severity
from app.domain.events import LogEvent, MetricEvent
from app.domain.ingestion import (
    EventIngestionService,
    IngestionStatus,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
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
    async with maker() as db_session:
        yield db_session

    await engine.dispose()


def _ts() -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _base() -> dict:
    return {
        "timestamp": _ts(),
        "source": "uploaded:app.log",
        "source_type": "file",
        "source_id": "42",
        "environment": "production",
        "raw_data": {"original": True},
    }


async def _seed_project_with_service(session: AsyncSession) -> tuple[Project, Service]:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    await session.refresh(service)
    return project, service


@pytest.mark.asyncio
async def test_ingest_log_event_persists_with_service(session: AsyncSession) -> None:
    project, service = await _seed_project_with_service(session)
    svc = EventIngestionService(session)

    event = LogEvent(
        **_base(),
        service="payments-api",
        message="connection refused",
        severity=Severity.HIGH,
    )
    result = await svc.ingest_one(project.id, event)
    await session.commit()

    assert result.status is IngestionStatus.ACCEPTED
    assert result.event_id is not None
    assert result.service_id == service.id

    row = (
        await session.execute(select(Event).where(Event.id == result.event_id))
    ).scalar_one()
    assert row.message == "connection refused"
    assert row.severity is Severity.HIGH
    assert row.raw_data == {"original": True}
    stored_ts = row.timestamp
    if stored_ts.tzinfo is None:
        stored_ts = stored_ts.replace(tzinfo=UTC)
    assert stored_ts == _ts()
    assert row.project_id == project.id
    assert row.service_id == service.id


@pytest.mark.asyncio
async def test_ingest_without_service_name(session: AsyncSession) -> None:
    project, _service = await _seed_project_with_service(session)
    svc = EventIngestionService(session)

    event = MetricEvent(**_base(), metric_name="latency_ms", value=120.0)
    result = await svc.ingest_one(project.id, event)
    await session.commit()

    assert result.status is IngestionStatus.ACCEPTED
    assert result.service_id is None


@pytest.mark.asyncio
async def test_ingest_from_dict_validates_and_persists(session: AsyncSession) -> None:
    project, _service = await _seed_project_with_service(session)
    svc = EventIngestionService(session)

    payload = {
        **_base(),
        "event_type": "ALERT",
        "name": "HighErrorRate",
        "severity": "CRITICAL",
    }
    result = await svc.ingest_one(project.id, payload)
    await session.commit()

    assert result.status is IngestionStatus.ACCEPTED
    assert result.event_type == "ALERT"


@pytest.mark.asyncio
async def test_project_not_found(session: AsyncSession) -> None:
    svc = EventIngestionService(session)
    event = LogEvent(**_base(), message="x")

    result = await svc.ingest_one(9999, event)

    assert result.status is IngestionStatus.PROJECT_NOT_FOUND
    assert result.errors


@pytest.mark.asyncio
async def test_service_not_found(session: AsyncSession) -> None:
    project, _service = await _seed_project_with_service(session)
    svc = EventIngestionService(session)
    event = LogEvent(**_base(), service="missing-svc", message="x")

    result = await svc.ingest_one(project.id, event)

    assert result.status is IngestionStatus.SERVICE_NOT_FOUND
    assert "missing-svc" in result.errors[0]


@pytest.mark.asyncio
async def test_batch_ingest_partial_success(session: AsyncSession) -> None:
    project, _service = await _seed_project_with_service(session)
    svc = EventIngestionService(session)

    batch = await svc.ingest_batch(
        project.id,
        [
            LogEvent(**_base(), service="payments-api", message="ok"),
            LogEvent(**_base(), service="unknown", message="bad"),
            {"not": "an event"},
        ],
    )
    await session.commit()

    assert batch.total == 3
    assert batch.accepted == 1
    assert batch.rejected == 2
    assert batch.success is False

    by_index = {r.index: r for r in batch.results}
    assert by_index[0].status is IngestionStatus.ACCEPTED
    assert by_index[1].status is IngestionStatus.SERVICE_NOT_FOUND
    assert by_index[2].status is IngestionStatus.VALIDATION_ERROR

    count = (await session.execute(select(Event))).scalars().all()
    assert len(count) == 1
