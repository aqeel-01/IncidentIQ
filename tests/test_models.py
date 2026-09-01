"""Tests for the core ORM models.

Uses an in-memory SQLite database (shared via ``StaticPool``) with foreign keys
enabled, so relationships, constraints, defaults, and enum handling can be
exercised without a running PostgreSQL instance.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    ErrorGroup,
    Event,
    EventType,
    Incident,
    IncidentStatus,
    Organization,
    Project,
    Service,
    Severity,
    User,
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _make_project(session: AsyncSession) -> Project:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def test_organization_relationships(session: AsyncSession) -> None:
    org = Organization(name="Acme", slug="acme")
    org.users.append(User(email="a@acme.test", hashed_password="x", full_name="Ann"))
    org.projects.append(Project(name="Payments", slug="payments"))
    session.add(org)
    await session.commit()

    loaded = (
        await session.execute(select(Organization).where(Organization.slug == "acme"))
    ).scalar_one()
    assert len(loaded.users) == 1
    assert len(loaded.projects) == 1
    assert loaded.users[0].organization is loaded
    assert loaded.users[0].is_active is True
    assert loaded.created_at is not None and loaded.updated_at is not None


async def test_incident_defaults_and_enums(session: AsyncSession) -> None:
    project = await _make_project(session)
    service = Service(project_id=project.id, name="api")
    session.add(service)
    await session.commit()

    incident = Incident(
        project_id=project.id,
        service_id=service.id,
        title="Elevated 500s",
        environment="production",
        severity=Severity.HIGH,
        started_at=_utcnow(),
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)

    # Defaults applied.
    assert incident.status is IncidentStatus.OPEN
    assert incident.occurrence_count == 1
    assert incident.ended_at is None
    assert incident.created_at is not None
    # Enum round-trips as the enum type.
    assert incident.severity is Severity.HIGH
    # Relationship navigation.
    assert incident.service.name == "api"


async def test_error_group_unique_fingerprint_per_project(
    session: AsyncSession,
) -> None:
    project = await _make_project(session)
    now = _utcnow()
    session.add(
        ErrorGroup(
            project_id=project.id,
            fingerprint="abc123",
            normalized_message="User <id> failed payment",
            severity=Severity.MEDIUM,
            first_seen=now,
            last_seen=now,
        )
    )
    await session.commit()

    session.add(
        ErrorGroup(
            project_id=project.id,
            fingerprint="abc123",
            normalized_message="duplicate",
            severity=Severity.LOW,
            first_seen=now,
            last_seen=now,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_event_links_to_error_group_and_service(session: AsyncSession) -> None:
    project = await _make_project(session)
    service = Service(project_id=project.id, name="api")
    now = _utcnow()
    group = ErrorGroup(
        project=project,
        service=service,
        fingerprint="deadbeef",
        normalized_message="timeout",
        severity=Severity.HIGH,
        first_seen=now,
        last_seen=now,
    )
    event_row = Event(
        project=project,
        service=service,
        error_group=group,
        event_type=EventType.LOG,
        source="uploaded:app.log",
        source_type="file",
        timestamp=now,
        environment="production",
        severity=Severity.HIGH,
        message="Connection timed out",
        raw_data={"line": "..."},
        normalized_data={"template": "Connection timed out"},
    )
    session.add(event_row)
    await session.commit()

    # Eager-load the relationship (async sessions cannot lazy-load implicitly).
    loaded = (
        await session.execute(
            select(ErrorGroup)
            .options(selectinload(ErrorGroup.events))
            .where(ErrorGroup.id == group.id)
        )
    ).scalar_one()
    assert len(loaded.events) == 1
    assert loaded.events[0].event_type is EventType.LOG
    assert loaded.events[0].raw_data == {"line": "..."}
    # event_row retains its Python-assigned service (expire_on_commit=False).
    assert event_row.service.name == "api"


async def test_foreign_key_is_enforced(session: AsyncSession) -> None:
    # organization_id points to a non-existent organization.
    session.add(User(organization_id=9999, email="x@y.test", hashed_password="x"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
