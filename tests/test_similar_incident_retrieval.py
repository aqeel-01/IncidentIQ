"""Tests for similar incident retrieval service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.models import IncidentStatus, Organization, Project, Service, Severity
from app.db.models.investigation_job import (
    InvestigationJob,
    InvestigationJobStatus,
    InvestigationStage,
)
from app.domain.incidents import CreateIncidentInput, IncidentService
from app.domain.rca import RCAEngineResult, RCAResult, RCAService, RCAStatus
from app.domain.rca.types import Hypothesis
from app.domain.similar_incidents import (
    HISTORICAL_CONTEXT_DISCLAIMER,
    SimilarIncidentRetrievalConfig,
    SimilarIncidentRetrievalService,
)
from app.domain.timeline.service import TimelineService


@pytest.fixture
def retrieval_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        incident_similarity_min_score=0.55,
        incident_similarity_max_results=3,
    )


@pytest_asyncio.fixture
async def db_session(
    retrieval_settings: Settings,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        retrieval_settings.database_url,
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


def _engine_result() -> RCAEngineResult:
    return RCAEngineResult(
        result=RCAResult(
            status=RCAStatus.CONFIDENT,
            primary_hypothesis=Hypothesis(
                title="Deployment regression",
                description="Recent deployment preceded the first error spike.",
                confidence=0.82,
            ),
            confidence=0.82,
            evidence_quality=70,
        ),
        engine_version="1",
        prompt_version="v1",
        ai_provider="ollama",
        ai_model="fake-rca-model",
    )


@pytest.mark.asyncio
async def test_retrieval_returns_scored_similar_historical_incidents(
    db_session: AsyncSession,
) -> None:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    db_session.add(project)
    await db_session.flush()

    incident_service = IncidentService(db_session)
    historical = await incident_service.create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="connection timeout talking to database",
            environment="production",
            severity=Severity.HIGH,
            started_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
        )
    )
    historical.incident.status = IncidentStatus.RESOLVED
    await db_session.flush()

    current = await incident_service.create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="connection timeout talking to database",
            environment="production",
            severity=Severity.HIGH,
            started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )
    )
    await db_session.flush()

    job = InvestigationJob(
        id="history-job",
        project_id=project.id,
        incident_id=historical.incident.id,
        status=InvestigationJobStatus.COMPLETED,
        stage=InvestigationStage.COMPLETED,
        stage_artifacts={},
    )
    db_session.add(job)
    await db_session.flush()
    await RCAService(db_session).persist(
        project_id=project.id,
        incident_id=historical.incident.id,
        investigation_job_id=job.id,
        evidence_group_id=None,
        engine_result=_engine_result(),
    )
    await db_session.commit()

    timeline = await TimelineService(db_session).build(current.incident.id)
    assert timeline is not None

    retrieval = SimilarIncidentRetrievalService(
        db_session,
        config=SimilarIncidentRetrievalConfig(min_score=0.55, max_results=3),
    )
    matches = await retrieval.find_similar(
        incident=current.incident,
        timeline=timeline,
        service_names={service.id: service.name},
    )
    context = await retrieval.build_historical_context(
        incident=current.incident,
        timeline=timeline,
        service_names={service.id: service.name},
    )

    assert matches
    assert matches[0].incident_id == historical.incident.id
    assert matches[0].similarity_score >= 0.55
    assert matches[0].context_only is True
    assert matches[0].primary_hypothesis_title == "Deployment regression"
    assert context is not None
    assert context.related_incident_ids == [historical.incident.id]
    assert context.similar_incidents[0].similarity_score == matches[0].similarity_score
    assert HISTORICAL_CONTEXT_DISCLAIMER in context.notes[0]


@pytest.mark.asyncio
async def test_retrieval_ignores_unrelated_historical_incidents(
    db_session: AsyncSession,
) -> None:
    org = Organization(name="Acme", slug="acme")
    project = Project(name="Payments", slug="payments", organization=org)
    service = Service(name="payments-api", project=project)
    db_session.add(project)
    await db_session.flush()

    incident_service = IncidentService(db_session)
    unrelated = await incident_service.create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="marketing email delivery delay",
            environment="production",
            severity=Severity.LOW,
            started_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        )
    )
    unrelated.incident.status = IncidentStatus.RESOLVED

    current = await incident_service.create(
        CreateIncidentInput(
            project_id=project.id,
            service_id=service.id,
            title="connection timeout talking to database",
            environment="production",
            severity=Severity.HIGH,
            started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()

    timeline = await TimelineService(db_session).build(current.incident.id)
    assert timeline is not None

    retrieval = SimilarIncidentRetrievalService(
        db_session,
        config=SimilarIncidentRetrievalConfig(min_score=0.55, max_results=3),
    )
    matches = await retrieval.find_similar(
        incident=current.incident,
        timeline=timeline,
        service_names={service.id: service.name},
    )

    assert matches == []
