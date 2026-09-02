"""Tests for the incident timeline service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    ErrorGroup,
    Incident,
    IncidentStatus,
    Organization,
    Project,
    Service,
    Severity,
)
from app.domain.events import (
    AlertEvent,
    AlertStatus,
    DeploymentEvent,
    LogEvent,
    MetricEvent,
    TraceEvent,
)
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.ingestion import EventIngestionService
from app.domain.timeline import TimelineCategory, TimelineService


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


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


def _base_event_fields() -> dict:
    return {
        "source": "test",
        "source_type": "test",
        "environment": "production",
        "raw_data": {"seed": True},
    }


async def _seed_timeline_data(
    session: AsyncSession,
) -> tuple[Incident, dict[str, int]]:
    project, service = await _seed_project(session)
    ingestion = EventIngestionService(session)

    events = [
        DeploymentEvent(
            timestamp=_ts(-60),
            version="v1.2.2",
            commit_sha="deploy123",
            repository="payments-api",
            service="payments-api",
            source="azure_devops:pipelines",
            source_type="azure_devops",
            environment="production",
            raw_data={"seed": True},
        ),
        MetricEvent(
            timestamp=_ts(-10),
            metric_name="error_rate",
            value=0.02,
            service="payments-api",
            **_base_event_fields(),
        ),
        LogEvent(
            timestamp=_ts(0),
            message="connection timeout talking to database",
            severity=Severity.HIGH,
            service="payments-api",
            **_base_event_fields(),
        ),
        AlertEvent(
            timestamp=_ts(5),
            name="HighErrorRate",
            status=AlertStatus.FIRING,
            severity=Severity.HIGH,
            service="payments-api",
            **_base_event_fields(),
        ),
        LogEvent(
            timestamp=_ts(10),
            message="retry succeeded",
            severity=Severity.INFO,
            service="payments-api",
            **_base_event_fields(),
        ),
        TraceEvent(
            timestamp=_ts(12),
            trace_id="trace-1",
            span_id="span-1",
            operation_name="checkout",
            duration_ms=250.0,
            service="payments-api",
            **_base_event_fields(),
        ),
        AlertEvent(
            timestamp=_ts(20),
            name="HighErrorRate",
            status=AlertStatus.RESOLVED,
            severity=Severity.HIGH,
            service="payments-api",
            **_base_event_fields(),
        ),
    ]

    event_ids: dict[str, int] = {}
    for item in events:
        result = await ingestion.ingest_one(project.id, item)
        assert result.event_id is not None
        event_ids[item.event_type.value] = result.event_id

    error_group = ErrorGroup(
        project_id=project.id,
        service_id=service.id,
        fingerprint="a" * 64,
        normalized_message="connection timeout talking to database",
        occurrence_count=3,
        first_seen=_ts(0),
        last_seen=_ts(10),
        severity=Severity.HIGH,
    )
    session.add(error_group)
    await session.flush()

    incident_result = await IncidentService(session).create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="Elevated checkout errors",
            environment="production",
            severity=Severity.HIGH,
            started_at=_ts(0),
            ended_at=_ts(25),
            status=IncidentStatus.RESOLVED,
        )
    )
    await session.commit()

    event_ids["error_group"] = error_group.id
    return incident_result.incident, event_ids


@pytest.mark.asyncio
async def test_timeline_orders_entries_chronologically(session: AsyncSession) -> None:
    incident, _event_ids = await _seed_timeline_data(session)

    timeline = await TimelineService(session).build(incident.id)
    assert timeline is not None

    timestamps = [entry.timestamp for entry in timeline.entries]
    assert timestamps == sorted(timestamps)
    assert timeline.counts["alert"] == 2
    assert timeline.counts["deployment"] == 1
    assert timeline.counts["error"] == 1
    assert timeline.counts["log"] == 2
    assert timeline.counts["metric"] == 1
    assert timeline.counts["trace"] == 1


@pytest.mark.asyncio
async def test_timeline_identifies_key_markers(session: AsyncSession) -> None:
    incident, event_ids = await _seed_timeline_data(session)

    timeline = await TimelineService(session).build(incident.id)
    assert timeline is not None
    markers = timeline.markers

    assert markers.first_anomaly is not None
    assert markers.first_anomaly.category is TimelineCategory.METRIC
    assert markers.first_anomaly.event_id == event_ids["METRIC"]

    assert markers.first_relevant_error is not None
    assert markers.first_relevant_error.category is TimelineCategory.ERROR
    assert markers.first_relevant_error.error_group_id == event_ids["error_group"]

    assert markers.first_alert is not None
    assert markers.first_alert.category is TimelineCategory.ALERT
    assert markers.first_alert.title == "HighErrorRate"

    assert markers.recent_deployment is not None
    assert markers.recent_deployment.category is TimelineCategory.DEPLOYMENT
    assert markers.recent_deployment.title == "v1.2.2 deploy123"

    assert markers.recovery is not None
    assert markers.recovery.title == "Incident resolved"
    assert markers.recovery.timestamp == _ts(25)


@pytest.mark.asyncio
async def test_timeline_returns_none_for_missing_incident(
    session: AsyncSession,
) -> None:
    result = await TimelineService(session).build(999)
    assert result is None


@pytest.mark.asyncio
async def test_timeline_normalizes_naive_timestamps_to_utc(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    naive_start = datetime(2026, 9, 1, 12, 0)
    incident = Incident(
        project_id=project.id,
        service_id=service.id,
        title="Naive timestamp incident",
        environment="production",
        fingerprint="b" * 64,
        severity=Severity.MEDIUM,
        status=IncidentStatus.OPEN,
        started_at=naive_start,
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)

    timeline = await TimelineService(session).build(incident.id)
    assert timeline is not None
    assert timeline.started_at.tzinfo is not None
    assert timeline.started_at.utcoffset() == timedelta(0)
