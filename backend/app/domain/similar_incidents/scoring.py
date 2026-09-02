"""Structured and embedding-based incident similarity scoring."""

from __future__ import annotations

from app.domain.deduplication.similarity import compute_message_similarity
from app.domain.similar_incidents.config import SimilarIncidentRetrievalConfig
from app.domain.similar_incidents.embeddings import cosine_similarity
from app.domain.similar_incidents.types import (
    IncidentSimilarityProfile,
    SimilarIncidentMatch,
)

HISTORICAL_CONTEXT_DISCLAIMER = (
    "Historical similar incidents are contextual references only; "
    "they are not proof of root cause for the current incident."
)


def build_embedding_text(
    *,
    title: str,
    problem_identity: str,
    environment: str,
    service_name: str | None,
    error_group_titles: list[str],
    symptom_titles: list[str],
    primary_hypothesis_title: str | None,
) -> str:
    parts = [
        title,
        problem_identity,
        environment,
        service_name or "",
        *error_group_titles,
        *symptom_titles,
        primary_hypothesis_title or "",
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _jaccard_similarity(left: list[str], right: list[str]) -> float:
    left_set = {item.casefold() for item in left if item}
    right_set = {item.casefold() for item in right if item}
    if not left_set or not right_set:
        return 0.0
    intersection = left_set & right_set
    union = left_set | right_set
    return len(intersection) / len(union)


def score_incident_similarity(
    source: IncidentSimilarityProfile,
    candidate: IncidentSimilarityProfile,
    *,
    config: SimilarIncidentRetrievalConfig,
) -> SimilarIncidentMatch | None:
    """Score a historical incident against the current incident profile."""

    matching_signals: list[str] = []

    title_score = compute_message_similarity(
        source.problem_identity,
        candidate.problem_identity,
    )
    if title_score >= 0.75:
        matching_signals.append("title")

    embedding_score = cosine_similarity(
        source.embedding_text,
        candidate.embedding_text,
    )
    if embedding_score >= 0.5:
        matching_signals.append("embedding")

    fingerprint_score = (
        1.0 if source.fingerprint == candidate.fingerprint else 0.0
    )
    if fingerprint_score == 1.0:
        matching_signals.append("fingerprint")

    service_score = (
        1.0
        if source.service_id is not None
        and candidate.service_id is not None
        and source.service_id == candidate.service_id
        else 0.0
    )
    if service_score == 1.0:
        matching_signals.append("service")

    environment_score = (
        1.0
        if source.environment.casefold() == candidate.environment.casefold()
        else 0.0
    )
    if environment_score == 1.0:
        matching_signals.append("environment")

    error_group_score = _jaccard_similarity(
        source.error_group_titles,
        candidate.error_group_titles,
    )
    if error_group_score > 0.0:
        matching_signals.append("error_groups")

    weighted_score = (
        title_score * config.title_weight
        + embedding_score * config.embedding_weight
        + fingerprint_score * config.fingerprint_weight
        + service_score * config.service_weight
        + environment_score * config.environment_weight
        + error_group_score * config.error_group_weight
    )
    if fingerprint_score == 1.0:
        weighted_score = max(weighted_score, 0.95)

    similarity_score = round(min(weighted_score, 1.0), 4)
    if similarity_score < config.min_score:
        return None

    return SimilarIncidentMatch(
        incident_id=candidate.incident_id,
        title=candidate.title,
        similarity_score=similarity_score,
        environment=candidate.environment,
        service=candidate.service_name,
        status=candidate.status,
        started_at=candidate.started_at,
        primary_hypothesis_title=candidate.primary_hypothesis_title,
        matching_signals=sorted(set(matching_signals)),
        context_only=True,
    )


def rank_similar_incidents(
    source: IncidentSimilarityProfile,
    candidates: list[IncidentSimilarityProfile],
    *,
    config: SimilarIncidentRetrievalConfig,
) -> list[SimilarIncidentMatch]:
    """Return scored historical incidents sorted by descending similarity."""

    matches: list[SimilarIncidentMatch] = []
    for candidate in candidates:
        if candidate.incident_id == source.incident_id:
            continue
        match = score_incident_similarity(source, candidate, config=config)
        if match is not None:
            matches.append(match)

    matches.sort(
        key=lambda item: (
            -item.similarity_score,
            item.started_at,
            item.incident_id,
        )
    )
    return matches[: config.max_results]
