"""Tests for incident deduplication."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    Incident,
    IncidentStatus,
    Organization,
    Project,
    Service,
    Severity,
)
from app.domain.incident_fingerprinting import (
    compute_incident_fingerprint_from_title,
    problem_identity_from_title,
)
from app.domain.incidents import (
    CreateIncidentInput,
    IncidentCreateAction,
    IncidentService,
    merge_incident_occurrence,
)


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, minutes, tzinfo=UTC)


def test_problem_identity_normalizes_dynamic_values() -> None:
    assert problem_identity_from_title("User 123 failed payment") == (
        "User {id} failed payment"
    )


def test_incident_fingerprint_uses_service_environment_and_identity() -> None:
    baseline = compute_incident_fingerprint_from_title(
        service_id=1,
        environment="Production",
        title="User 123 failed payment",
    )
    same_logical = compute_incident_fingerprint_from_title(
        service_id=1,
        environment="production",
        title="User 456 failed payment",
    )
    different_service = compute_incident_fingerprint_from_title(
        service_id=2,
        environment="production",
        title="User 789 failed payment",
    )

    assert baseline == same_logical
    assert baseline != different_service


def test_merge_incident_occurrence_updates_count_and_started_at() -> None:
    count, started_at = merge_incident_occurrence(
        occurrence_count=2,
        started_at=_ts(10),
        event_started_at=_ts(5),
    )
    assert count == 3
    assert started_at == _ts(5)


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


async def _seed_project(session: AsyncSession) -> tuple[Project, Service]:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    await session.refresh(service)
    return project, service


def _input(
    *,
    project_id: int,
    service_id: int | None,
    title: str,
    environment: str = "production",
    started_at: datetime | None = None,
    status: IncidentStatus = IncidentStatus.OPEN,
) -> CreateIncidentInput:
    return CreateIncidentInput(
        project_id=project_id,
        service_id=service_id,
        title=title,
        environment=environment,
        severity=Severity.HIGH,
        status=status,
        started_at=started_at or _ts(),
    )


@pytest.mark.asyncio
async def test_repeated_incidents_merge_into_active_incident(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    svc = IncidentService(session)

    first = await svc.create(
        _input(
            project_id=project.id,
            service_id=service.id,
            title="User 100 failed payment",
            started_at=_ts(0),
        )
    )
    second = await svc.create(
        _input(
            project_id=project.id,
            service_id=service.id,
            title="User 200 failed payment",
            started_at=_ts(5),
        )
    )
    await session.commit()

    assert first.action is IncidentCreateAction.CREATED
    assert second.action is IncidentCreateAction.MERGED
    assert second.incident.id == first.incident.id
    assert second.incident.occurrence_count == 2
    assert second.incident.started_at.replace(tzinfo=UTC) == _ts(0)

    count = (
        await session.execute(select(func.count()).select_from(Incident))
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_independent_incidents_remain_separate(session: AsyncSession) -> None:
    project, service = await _seed_project(session)
    svc = IncidentService(session)

    payment = await svc.create(
        _input(
            project_id=project.id,
            service_id=service.id,
            title="User 100 failed payment",
            environment="production",
        )
    )
    timeout = await svc.create(
        _input(
            project_id=project.id,
            service_id=service.id,
            title="Connection 42 timed out",
            environment="production",
        )
    )
    staging = await svc.create(
        _input(
            project_id=project.id,
            service_id=service.id,
            title="User 300 failed payment",
            environment="staging",
        )
    )
    await session.commit()

    assert payment.action is IncidentCreateAction.CREATED
    assert timeout.action is IncidentCreateAction.CREATED
    assert staging.action is IncidentCreateAction.CREATED
    assert payment.incident.id != timeout.incident.id != staging.incident.id

    count = (
        await session.execute(select(func.count()).select_from(Incident))
    ).scalar_one()
    assert count == 3


@pytest.mark.asyncio
async def test_resolved_incident_allows_new_active_duplicate(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    svc = IncidentService(session)

    resolved = await svc.create(
        _input(
            project_id=project.id,
            service_id=service.id,
            title="User 100 failed payment",
            status=IncidentStatus.RESOLVED,
            started_at=_ts(0),
        )
    )
    reopened = await svc.create(
        _input(
            project_id=project.id,
            service_id=service.id,
            title="User 200 failed payment",
            started_at=_ts(10),
        )
    )
    await session.commit()

    assert resolved.action is IncidentCreateAction.CREATED
    assert reopened.action is IncidentCreateAction.CREATED
    assert reopened.incident.id != resolved.incident.id

    count = (
        await session.execute(select(func.count()).select_from(Incident))
    ).scalar_one()
    assert count == 2
