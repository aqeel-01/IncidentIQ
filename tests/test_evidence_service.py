"""Tests for evidence persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import EvidenceGroup as EvidenceGroupRow
from app.db.models import (
    Incident,
    IncidentStatus,
    Organization,
    Project,
    Service,
    Severity,
)
from app.domain.evidence import (
    EventReference,
    Evidence,
    EvidenceGroup,
    EvidenceRelation,
    EvidenceRelationKind,
    EvidenceService,
    EvidenceSource,
    EvidenceStance,
    build_evidence_group,
)
from tests.test_evidence_quality import _high_quality_timeline


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


async def _seed_incident(session: AsyncSession) -> Incident:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    session.add(project)
    await session.flush()

    incident = Incident(
        project_id=project.id,
        service_id=service.id,
        title="Checkout failures",
        environment="production",
        fingerprint="a" * 64,
        severity=Severity.HIGH,
        status=IncidentStatus.OPEN,
        started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)
    return incident


def _sample_package(incident: Incident) -> EvidenceGroup:
    return EvidenceGroup(
        incident_id=incident.id,
        project_id=incident.project_id,
        built_at=datetime(2026, 9, 1, 12, 5, tzinfo=UTC),
        summary="test package",
        evidence=[
            Evidence(
                key="ev-1",
                source=EvidenceSource.DEPLOYMENT_CORRELATION,
                timestamp=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                event_reference=EventReference(timeline_entry_id="event:1"),
                description="Deployment preceded error",
                value="deployment_before_first_error",
                confidence=0.8,
                supporting_or_contradicting=EvidenceStance.SUPPORTING,
            ),
            Evidence(
                key="ev-2",
                source=EvidenceSource.DEPLOYMENT_CORRELATION,
                timestamp=datetime(2026, 9, 1, 12, 1, tzinfo=UTC),
                event_reference=EventReference(timeline_entry_id="error_group:1"),
                description="Error observed after deployment",
                confidence=0.6,
                supporting_or_contradicting=EvidenceStance.CONTRADICTING,
            ),
        ],
        relations=[
            EvidenceRelation(
                key="rel-1",
                source_evidence_key="ev-1",
                target_evidence_key="ev-2",
                kind=EvidenceRelationKind.CONTRADICTS,
                confidence=0.5,
                description="Mixed deployment signals",
            )
        ],
    )


@pytest.mark.asyncio
async def test_persist_and_reload_evidence_group(session: AsyncSession) -> None:
    incident = await _seed_incident(session)
    service = EvidenceService(session)

    persisted = await service.persist(_sample_package(incident))
    await session.commit()

    assert persisted.id is not None
    assert len(persisted.evidence) == 2
    assert len(persisted.relations) == 1

    loaded = await service.get_latest_for_incident(incident.id)
    assert loaded is not None
    assert loaded.id == persisted.id
    assert loaded.evidence[0].description == "Deployment preceded error"
    assert loaded.evidence[0].supporting_or_contradicting is EvidenceStance.SUPPORTING
    assert loaded.relations[0].kind is EvidenceRelationKind.CONTRADICTS


@pytest.mark.asyncio
async def test_persist_and_reload_preserves_quality(session: AsyncSession) -> None:
    incident = await _seed_incident(session)
    timeline = _high_quality_timeline().model_copy(
        update={"incident_id": incident.id, "project_id": incident.project_id},
    )
    package = build_evidence_group(
        timeline,
        built_at=datetime(2026, 9, 1, 12, 5, tzinfo=UTC),
        service_names={1: "payments-api"},
    )
    service = EvidenceService(session)

    persisted = await service.persist(package)
    await session.commit()

    loaded = await service.get_latest_for_incident(incident.id)
    assert loaded is not None
    assert loaded.quality is not None
    assert loaded.quality.score == persisted.quality.score
    assert loaded.metadata.get("quality_score") == loaded.quality.score


@pytest.mark.asyncio
async def test_evidence_group_cascades_when_incident_deleted(
    session: AsyncSession,
) -> None:
    incident = await _seed_incident(session)
    await EvidenceService(session).persist(_sample_package(incident))
    await session.commit()

    await session.delete(incident)
    await session.commit()

    remaining = (await session.execute(select(EvidenceGroupRow))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent_package(session: AsyncSession) -> None:
    incident = await _seed_incident(session)
    service = EvidenceService(session)

    older = _sample_package(incident).model_copy(
        update={"built_at": datetime(2026, 9, 1, 12, 0, tzinfo=UTC), "summary": "old"}
    )
    newer = _sample_package(incident).model_copy(
        update={
            "built_at": datetime(2026, 9, 1, 12, 10, tzinfo=UTC),
            "summary": "new",
        }
    )
    await service.persist(older)
    await service.persist(newer)
    await session.commit()

    latest = await service.get_latest_for_incident(incident.id)
    assert latest is not None
    assert latest.summary == "new"
