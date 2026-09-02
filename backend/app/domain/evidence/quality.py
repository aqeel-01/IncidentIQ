"""Evidence quality scoring from structured evidence packages."""

from __future__ import annotations

from app.domain.evidence.types import (
    EvidenceGraphNodeKind,
    EvidenceGroup,
    EvidenceQualityAssessment,
    EvidenceQualityBreakdown,
    EvidenceRelationKind,
    EvidenceSource,
    EvidenceStance,
)

_SOURCE_COUNT = len(EvidenceSource)
_IDEAL_CHAIN_LENGTH = len(EvidenceGraphNodeKind)


def score_evidence_quality(package: EvidenceGroup) -> EvidenceQualityAssessment:
    """Score an evidence package on a deterministic 0-100 scale."""

    breakdown = EvidenceQualityBreakdown(
        source_diversity=_score_source_diversity(package),
        temporal_consistency=_score_temporal_consistency(package),
        correlation_strength=_score_correlation_strength(package),
        completeness=_score_completeness(package),
        consistency=_score_consistency(package),
    )
    overall = (
        breakdown.source_diversity
        + breakdown.temporal_consistency
        + breakdown.correlation_strength
        + breakdown.completeness
        + breakdown.consistency
    ) / 5.0
    score = int(round(overall))

    return EvidenceQualityAssessment(
        score=score,
        breakdown=breakdown,
        summary=_build_quality_summary(score, breakdown),
    )


def _score_source_diversity(package: EvidenceGroup) -> float:
    unique_sources = {item.source for item in package.evidence}
    if not unique_sources:
        return 0.0
    return round((len(unique_sources) / _SOURCE_COUNT) * 100.0, 2)


def _score_temporal_consistency(package: EvidenceGroup) -> float:
    graph = package.evidence_graph
    if graph is None or len(graph.chain) < 2:
        return 50.0 if package.evidence else 0.0

    nodes_by_id = {node.id: node for node in graph.nodes}
    ordered = [
        nodes_by_id[node_id]
        for node_id in graph.chain
        if node_id in nodes_by_id
    ]
    if len(ordered) < 2:
        return 50.0

    consistent_pairs = sum(
        1
        for earlier, later in zip(ordered, ordered[1:], strict=False)
        if earlier.timestamp <= later.timestamp
    )
    return round((consistent_pairs / (len(ordered) - 1)) * 100.0, 2)


def _score_correlation_strength(package: EvidenceGroup) -> float:
    scores: list[float] = [relation.confidence for relation in package.relations]
    if package.evidence_graph is not None:
        scores.extend(edge.confidence for edge in package.evidence_graph.edges)

    if not scores:
        analytical = [
            item.confidence
            for item in package.evidence
            if item.source is not EvidenceSource.TIMELINE_MARKER
        ]
        if not analytical:
            return 0.0
        scores = analytical

    return round((sum(scores) / len(scores)) * 100.0, 2)


def _score_completeness(package: EvidenceGroup) -> float:
    graph = package.evidence_graph
    chain_score = 0.0
    if graph is not None and _IDEAL_CHAIN_LENGTH > 0:
        chain_score = min(100.0, (len(graph.chain) / _IDEAL_CHAIN_LENGTH) * 100.0)

    relation_score = min(100.0, len(package.relations) * 20.0)
    evidence_score = min(100.0, len(package.evidence) * 5.0)

    return round(
        (0.6 * chain_score) + (0.2 * relation_score) + (0.2 * evidence_score),
        2,
    )


def _score_consistency(package: EvidenceGroup) -> float:
    supporting = sum(
        1
        for item in package.evidence
        if item.supporting_or_contradicting is EvidenceStance.SUPPORTING
    )
    contradicting = sum(
        1
        for item in package.evidence
        if item.supporting_or_contradicting is EvidenceStance.CONTRADICTING
    )
    neutral = sum(
        1
        for item in package.evidence
        if item.supporting_or_contradicting is EvidenceStance.NEUTRAL
    )

    if supporting + contradicting == 0:
        stance_score = 100.0 if neutral > 0 else 50.0
    else:
        stance_score = (supporting / (supporting + contradicting)) * 100.0

    contradict_relations = sum(
        1
        for relation in package.relations
        if relation.kind is EvidenceRelationKind.CONTRADICTS
    )
    relation_penalty = min(50.0, contradict_relations * 15.0)

    return round(max(0.0, stance_score - relation_penalty), 2)


def _build_quality_summary(score: int, breakdown: EvidenceQualityBreakdown) -> str:
    if score >= 75:
        level = "high"
    elif score >= 45:
        level = "medium"
    else:
        level = "low"

    weakest = min(
        (
            ("source diversity", breakdown.source_diversity),
            ("temporal consistency", breakdown.temporal_consistency),
            ("correlation strength", breakdown.correlation_strength),
            ("completeness", breakdown.completeness),
            ("consistency", breakdown.consistency),
        ),
        key=lambda item: item[1],
    )
    return (
        f"{level.capitalize()} evidence quality ({score}/100); "
        f"weakest dimension: {weakest[0]} ({weakest[1]:.0f})"
    )
