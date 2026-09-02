"""Tests for evidence domain models and engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.correlation import (
    CorrelationKind,
    DeploymentCorrelationAssessment,
    TemporalCorrelation,
)
from app.domain.correlation.types import DeploymentEvidence, DeploymentEvidenceKind
from app.domain.evidence import (
    EvidenceGroup,
    EvidenceSource,
    EvidenceStance,
    build_evidence_group,
)
from app.domain.timeline.types import (
    TimelineCategory,
    TimelineEntry,
    TimelineMarkers,
    TimelineResult,
)


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _entry(
    entry_id: str,
    category: TimelineCategory,
    *,
    minutes: int = 0,
    title: str = "event",
    metadata: dict | None = None,
) -> TimelineEntry:
    return TimelineEntry(
        id=entry_id,
        category=category,
        timestamp=_ts(minutes),
        title=title,
        metadata=metadata or {},
    )


def _timeline(**overrides) -> TimelineResult:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-30,
        title="v1.2.2",
    )
    error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="database timeout",
        metadata={"service_id": 1},
    )
    correlation = TemporalCorrelation(
        kind=CorrelationKind.DEPLOYMENT_TO_ERROR,
        source=deployment,
        target=error,
        time_difference=timedelta(minutes=30),
        correlation_score=0.75,
        reason="Deployment preceded error",
    )
    base = {
        "incident_id": 1,
        "project_id": 1,
        "started_at": _ts(0),
        "ended_at": None,
        "window_start": _ts(-60),
        "window_end": _ts(60),
        "entries": [deployment, error],
        "markers": TimelineMarkers(
            recent_deployment=deployment,
            first_relevant_error=error,
        ),
        "counts": {"deployment": 1, "error": 1},
        "correlations": [correlation],
        "deployment_correlation": DeploymentCorrelationAssessment(
            is_related=True,
            relationship_score=0.7,
            deployment=deployment,
            supporting_evidence=[
                DeploymentEvidence(
                    kind=DeploymentEvidenceKind.DEPLOYMENT_BEFORE_FIRST_ERROR,
                    detail="Deployment preceded first error",
                    weight=0.35,
                )
            ],
            contradicting_evidence=[
                DeploymentEvidence(
                    kind=DeploymentEvidenceKind.DEPLOYMENT_ALONE_INSUFFICIENT,
                    detail="Deployment alone is insufficient",
                    weight=0.3,
                )
            ],
            summary="Possible deployment association",
        ),
    }
    base.update(overrides)
    return TimelineResult(**base)


def test_build_evidence_group_contains_required_fields() -> None:
    package = build_evidence_group(_timeline(), built_at=_ts(0))

    assert isinstance(package, EvidenceGroup)
    assert package.incident_id == 1
    assert package.evidence
    assert package.relations

    item = next(
        evidence
        for evidence in package.evidence
        if evidence.source is EvidenceSource.TEMPORAL_CORRELATION
    )
    assert item.description
    assert item.confidence == 0.75
    assert item.event_reference.timeline_entry_id == "event:1"
    assert item.supporting_or_contradicting is EvidenceStance.SUPPORTING


def test_build_evidence_group_creates_supporting_and_contradicting_items() -> None:
    package = build_evidence_group(_timeline(), built_at=_ts(0))

    stances = {item.supporting_or_contradicting for item in package.evidence}
    assert EvidenceStance.SUPPORTING in stances
    assert EvidenceStance.CONTRADICTING in stances

    assert any(
        relation.kind.value == "contradicts" for relation in package.relations
    )


def test_build_evidence_group_includes_metric_anomalies() -> None:
    anomaly = _entry(
        "event:2",
        TimelineCategory.METRIC,
        minutes=-5,
        title="error_rate",
        metadata={
            "anomaly": True,
            "normalized_data": {"metric_name": "error_rate", "value": 0.9},
        },
    )
    timeline = _timeline(entries=[*_timeline().entries, anomaly])

    package = build_evidence_group(timeline, built_at=_ts(0))
    assert any(
        item.source is EvidenceSource.ANOMALY_DETECTION for item in package.evidence
    )


def test_build_evidence_group_includes_timeline_markers() -> None:
    package = build_evidence_group(_timeline(), built_at=_ts(0))

    assert any(
        item.source is EvidenceSource.TIMELINE_MARKER for item in package.evidence
    )
    marker = next(
        item
        for item in package.evidence
        if item.source is EvidenceSource.TIMELINE_MARKER
        and item.description.startswith("Timeline marker")
    )
    assert marker.supporting_or_contradicting is EvidenceStance.NEUTRAL


def test_build_evidence_group_includes_evidence_graph() -> None:
    package = build_evidence_group(_timeline(), built_at=_ts(0))

    assert package.evidence_graph is not None
    assert package.evidence_graph.incident_id == 1
    assert any(
        node.kind.value == "incident" for node in package.evidence_graph.nodes
    )


def test_build_evidence_group_includes_quality_assessment() -> None:
    package = build_evidence_group(_timeline(), built_at=_ts(0))

    assert package.quality is not None
    assert 0 <= package.quality.score <= 100
    assert package.metadata.get("quality_score") == package.quality.score
