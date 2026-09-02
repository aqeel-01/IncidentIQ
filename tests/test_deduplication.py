"""Tests for duplicate event merging into error groups."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import ErrorGroup, Organization, Project, Service, Severity
from app.domain.deduplication import (
    ErrorGroupDeduplicationService,
    ErrorGroupEventInput,
    MergeAction,
    error_group_input_from_normalized,
    merge_error_group_timestamps,
)
from app.domain.events import LogEvent
from app.domain.fingerprinting import (
    compute_event_fingerprint,
    compute_logical_error_fingerprint,
    fingerprint_log_event,
    fingerprint_logical_log_event,
)
from app.domain.normalization import normalize_log_event, normalize_parsed_record
from app.domain.parsing.types import LogFormat, ParsedLogRecord


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, minutes, tzinfo=UTC)


def _event_input(
    *,
    source: str = "uploaded:app.log",
    message: str = "User {id} failed payment",
    timestamp: datetime | None = None,
    project_id: int = 1,
    service_id: int | None = 1,
) -> ErrorGroupEventInput:
    return ErrorGroupEventInput(
        project_id=project_id,
        timestamp=timestamp or _ts(),
        severity=Severity.HIGH,
        normalized_message=message,
        service_id=service_id,
        service="payments-api",
        source=source,
    )


def test_merge_error_group_timestamps_updates_bounds() -> None:
    count, first_seen, last_seen = merge_error_group_timestamps(
        occurrence_count=2,
        first_seen=_ts(10),
        last_seen=_ts(20),
        event_timestamp=_ts(5),
    )
    assert count == 3
    assert first_seen == _ts(5)
    assert last_seen == _ts(20)

    count, first_seen, last_seen = merge_error_group_timestamps(
        occurrence_count=2,
        first_seen=_ts(10),
        last_seen=_ts(20),
        event_timestamp=_ts(30),
    )
    assert count == 3
    assert first_seen == _ts(10)
    assert last_seen == _ts(30)


def test_logical_fingerprint_ignores_source_for_cross_source_dedup() -> None:
    logical = compute_logical_error_fingerprint(
        event_type="LOG",
        service="payments-api",
        severity=Severity.HIGH,
        normalized_message="User {id} failed payment",
    )
    with_other_source = compute_event_fingerprint(
        event_type="LOG",
        source="opensearch:payments",
        service="payments-api",
        severity=Severity.HIGH,
        normalized_message="User {id} failed payment",
    )
    assert logical != with_other_source

    event_a = normalize_log_event(
        LogEvent(
            timestamp=_ts(),
            source="uploaded:app.log",
            source_type="file",
            message="User 123 failed payment",
            service="payments-api",
            severity=Severity.HIGH,
            raw_data={},
        )
    )
    event_b = normalize_log_event(
        LogEvent(
            timestamp=_ts(),
            source="opensearch:payments",
            source_type="opensearch",
            message="User 456 failed payment",
            service="payments-api",
            severity=Severity.HIGH,
            raw_data={},
        )
    )
    assert fingerprint_logical_log_event(event_a) == fingerprint_logical_log_event(
        event_b
    )
    assert fingerprint_log_event(event_a) != fingerprint_log_event(event_b)


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


@pytest.mark.asyncio
async def test_repeated_events_merge_into_single_error_group(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    dedup = ErrorGroupDeduplicationService(session)

    first = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            timestamp=_ts(0),
            message="User {id} failed payment",
        )
    )
    second = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            timestamp=_ts(5),
            message="User {id} failed payment",
        )
    )
    third = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            timestamp=_ts(10),
            message="User {id} failed payment",
        )
    )
    await session.commit()

    assert first.action is MergeAction.CREATED
    assert second.action is MergeAction.MERGED
    assert third.action is MergeAction.MERGED
    assert second.error_group_id == first.error_group_id == third.error_group_id
    assert third.occurrence_count == 3
    assert third.first_seen == _ts(0)
    assert third.last_seen == _ts(10)

    count = (
        await session.execute(select(func.count()).select_from(ErrorGroup))
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_cross_source_events_merge_without_duplicate_groups(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    dedup = ErrorGroupDeduplicationService(session)

    upload = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            source="uploaded:app.log",
            timestamp=_ts(1),
        )
    )
    opensearch = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            source="opensearch:payments",
            timestamp=_ts(8),
        )
    )
    await session.commit()

    assert upload.action is MergeAction.CREATED
    assert opensearch.action is MergeAction.MERGED
    assert upload.error_group_id == opensearch.error_group_id
    assert opensearch.occurrence_count == 2
    assert opensearch.first_seen == _ts(1)
    assert opensearch.last_seen == _ts(8)

    groups = (await session.execute(select(ErrorGroup))).scalars().all()
    assert len(groups) == 1


@pytest.mark.asyncio
async def test_distinct_logical_errors_create_separate_groups(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    dedup = ErrorGroupDeduplicationService(session)

    payment = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="User {id} failed payment",
        )
    )
    timeout = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="connection {id} timed out",
        )
    )
    await session.commit()

    assert payment.action is MergeAction.CREATED
    assert timeout.action is MergeAction.CREATED
    assert payment.error_group_id != timeout.error_group_id
    assert payment.fingerprint != timeout.fingerprint

    count = (
        await session.execute(select(func.count()).select_from(ErrorGroup))
    ).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_merge_from_normalized_record_helper(session: AsyncSession) -> None:
    project, service = await _seed_project(session)
    parsed = ParsedLogRecord(
        line_number=1,
        format=LogFormat.JSONL,
        timestamp=_ts(),
        severity=Severity.HIGH,
        message="User 999 failed payment",
        service="payments-api",
        raw_data={"k": "v"},
    )
    normalized = normalize_parsed_record(parsed)
    event_input = error_group_input_from_normalized(
        normalized,
        project_id=project.id,
        source="uploaded:app.log",
        service_id=service.id,
    )

    result = await ErrorGroupDeduplicationService(session).merge(event_input)
    await session.commit()

    assert result.action is MergeAction.CREATED
    assert result.occurrence_count == 1
