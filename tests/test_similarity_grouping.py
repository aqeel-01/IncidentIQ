"""Tests for similar error grouping and investigation candidates."""

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
    ErrorGroup,
    ErrorGroupSimilarityCandidate,
    Organization,
    Project,
    Service,
    Severity,
)
from app.domain.deduplication import (
    ErrorGroupDeduplicationService,
    ErrorGroupEventInput,
    MergeAction,
    SimilarityClassification,
    SimilarityThresholds,
    classify_similarity,
    compute_message_similarity,
    find_best_similar_match,
)
from app.domain.deduplication.similarity import SimilarityCandidateGroup


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, minutes, tzinfo=UTC)


def _thresholds() -> SimilarityThresholds:
    return SimilarityThresholds(high_confidence_min=0.90, possible_match_min=0.70)


def _event_input(
    *,
    source: str = "uploaded:app.log",
    message: str,
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


def test_compute_message_similarity_identical_messages_score_one() -> None:
    message = "payment failed for user {id}"
    assert compute_message_similarity(message, message) == 1.0


def test_classify_similarity_respects_configurable_thresholds() -> None:
    thresholds = _thresholds()

    assert (
        classify_similarity(0.95, thresholds)
        is SimilarityClassification.HIGH_CONFIDENCE
    )
    assert (
        classify_similarity(0.82, thresholds) is SimilarityClassification.POSSIBLE_MATCH
    )
    assert classify_similarity(0.50, thresholds) is SimilarityClassification.NO_MATCH


def test_find_best_similar_match_returns_highest_scoring_candidate() -> None:
    thresholds = _thresholds()
    match = find_best_similar_match(
        normalized_message="payment failed for user {id}",
        candidates=[
            SimilarityCandidateGroup(
                error_group_id=1,
                normalized_message="database disk full",
            ),
            SimilarityCandidateGroup(
                error_group_id=2,
                normalized_message="payment failed for user {id} on checkout",
            ),
        ],
        thresholds=thresholds,
    )

    assert match is not None
    assert match.error_group_id == 2
    assert match.classification is SimilarityClassification.POSSIBLE_MATCH


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
async def test_high_confidence_similar_errors_merge_automatically(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    dedup = ErrorGroupDeduplicationService(session, similarity_thresholds=_thresholds())

    baseline = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="unable to acquire database connection",
            timestamp=_ts(0),
        )
    )
    similar = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="unable to acquire database connection pool",
            timestamp=_ts(5),
        )
    )
    await session.commit()

    assert baseline.action is MergeAction.CREATED
    assert similar.action is MergeAction.MERGED
    assert similar.error_group_id == baseline.error_group_id
    assert similar.similarity_match is not None
    assert (
        similar.similarity_match.classification
        is SimilarityClassification.HIGH_CONFIDENCE
    )
    assert similar.similarity_match.similarity_score >= 0.90

    group_count = (
        await session.execute(select(func.count()).select_from(ErrorGroup))
    ).scalar_one()
    assert group_count == 1

    candidate_count = (
        await session.execute(
            select(func.count()).select_from(ErrorGroupSimilarityCandidate)
        )
    ).scalar_one()
    assert candidate_count == 0


@pytest.mark.asyncio
async def test_possible_match_creates_separate_group_and_investigation_candidate(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    dedup = ErrorGroupDeduplicationService(session, similarity_thresholds=_thresholds())

    baseline = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="payment failed for user {id}",
            timestamp=_ts(0),
        )
    )
    uncertain = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="payment failed for user {id} on checkout",
            timestamp=_ts(5),
        )
    )
    await session.commit()

    assert baseline.action is MergeAction.CREATED
    assert uncertain.action is MergeAction.CREATED
    assert uncertain.error_group_id != baseline.error_group_id
    assert uncertain.investigation_candidate is not None
    assert (
        uncertain.investigation_candidate.classification
        is SimilarityClassification.POSSIBLE_MATCH
    )
    assert (
        uncertain.investigation_candidate.matched_error_group_id
        == baseline.error_group_id
    )

    group_count = (
        await session.execute(select(func.count()).select_from(ErrorGroup))
    ).scalar_one()
    assert group_count == 2

    stored = (await session.execute(select(ErrorGroupSimilarityCandidate))).scalar_one()
    assert stored.source_error_group_id == uncertain.error_group_id
    assert stored.candidate_error_group_id == baseline.error_group_id
    assert stored.similarity_score >= 0.70


@pytest.mark.asyncio
async def test_unrelated_errors_remain_separate_without_candidates(
    session: AsyncSession,
) -> None:
    project, service = await _seed_project(session)
    dedup = ErrorGroupDeduplicationService(session, similarity_thresholds=_thresholds())

    payment = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="user {id} failed payment",
        )
    )
    disk = await dedup.merge(
        _event_input(
            project_id=project.id,
            service_id=service.id,
            message="database disk full on host {ip}",
        )
    )
    await session.commit()

    assert payment.action is MergeAction.CREATED
    assert disk.action is MergeAction.CREATED
    assert payment.error_group_id != disk.error_group_id
    assert disk.investigation_candidate is None

    group_count = (
        await session.execute(select(func.count()).select_from(ErrorGroup))
    ).scalar_one()
    assert group_count == 2

    candidate_count = (
        await session.execute(
            select(func.count()).select_from(ErrorGroupSimilarityCandidate)
        )
    ).scalar_one()
    assert candidate_count == 0
