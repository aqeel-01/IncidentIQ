"""Tests for similar incident scoring and embeddings."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.similar_incidents.config import SimilarIncidentRetrievalConfig
from app.domain.similar_incidents.embeddings import cosine_similarity
from app.domain.similar_incidents.scoring import (
    HISTORICAL_CONTEXT_DISCLAIMER,
    rank_similar_incidents,
    score_incident_similarity,
)
from app.domain.similar_incidents.types import IncidentSimilarityProfile


def _profile(
    *,
    incident_id: int,
    title: str,
    problem_identity: str | None = None,
    fingerprint: str = "fp",
    service_id: int | None = 1,
    environment: str = "production",
    error_group_titles: list[str] | None = None,
    embedding_text: str | None = None,
    primary_hypothesis_title: str | None = None,
) -> IncidentSimilarityProfile:
    identity = problem_identity or title
    return IncidentSimilarityProfile(
        incident_id=incident_id,
        project_id=1,
        title=title,
        problem_identity=identity,
        fingerprint=fingerprint,
        environment=environment,
        service_id=service_id,
        service_name="payments-api",
        severity="HIGH",
        status="IDENTIFIED",
        started_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        error_group_titles=error_group_titles or [],
        symptom_titles=[],
        primary_hypothesis_title=primary_hypothesis_title,
        embedding_text=embedding_text or f"{title} {identity} production payments-api",
    )


def test_cosine_similarity_returns_higher_score_for_related_text() -> None:
    related = cosine_similarity(
        "checkout timeout database production",
        "checkout database timeout errors production",
    )
    unrelated = cosine_similarity(
        "checkout timeout database production",
        "marketing email campaign launch",
    )

    assert related > unrelated
    assert related > 0.0


def test_score_incident_similarity_marks_fingerprint_matches() -> None:
    source = _profile(
        incident_id=1,
        title="Checkout failures",
        fingerprint="same-fingerprint",
    )
    candidate = _profile(
        incident_id=2,
        title="Checkout failures last week",
        fingerprint="same-fingerprint",
    )

    match = score_incident_similarity(
        source,
        candidate,
        config=SimilarIncidentRetrievalConfig(min_score=0.5),
    )

    assert match is not None
    assert match.similarity_score >= 0.95
    assert "fingerprint" in match.matching_signals
    assert match.context_only is True


def test_rank_similar_incidents_excludes_current_incident_and_sorts() -> None:
    source = _profile(
        incident_id=1,
        title="connection timeout talking to database",
        problem_identity="connection timeout talking to database",
        fingerprint="fp-source",
    )
    strong = _profile(
        incident_id=2,
        title="connection timeout talking to database",
        problem_identity="connection timeout talking to database",
        fingerprint="fp-source",
        primary_hypothesis_title="Database saturation",
    )
    weak = _profile(
        incident_id=3,
        title="marketing email delivery delay",
        problem_identity="marketing email delivery delay",
        fingerprint="fp-weak",
        service_id=99,
        environment="staging",
        embedding_text="marketing email delivery delay staging",
    )

    matches = rank_similar_incidents(
        source,
        [source, strong, weak],
        config=SimilarIncidentRetrievalConfig(min_score=0.55, max_results=2),
    )

    assert [match.incident_id for match in matches] == [2]
    assert matches[0].similarity_score >= 0.55


def test_historical_context_disclaimer_states_context_only() -> None:
    assert "context" in HISTORICAL_CONTEXT_DISCLAIMER.casefold()
    assert "not proof" in HISTORICAL_CONTEXT_DISCLAIMER.casefold()
