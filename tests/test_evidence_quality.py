"""Tests for evidence quality scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.correlation import CorrelationKind, TemporalCorrelation
from app.domain.correlation.types import (
    DeploymentCorrelationAssessment,
    DeploymentEvidence,
    DeploymentEvidenceKind,
    ScoredServiceRelationship,
    ServiceCorrelationResult,
    ServiceRelationshipEvidence,
    ServiceRelationshipKind,
    ServiceRelationshipSignal,
)
from app.domain.evidence import (
    EventReference,
    Evidence,
    EvidenceGroup,
    EvidenceQualityAssessment,
    EvidenceRelation,
    EvidenceRelationKind,
    EvidenceSource,
    EvidenceStance,
    build_evidence_group,
    score_evidence_quality,
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


def _high_quality_timeline() -> TimelineResult:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-30,
        title="v1.2.2",
    )
    anomaly = _entry(
        "event:2",
        TimelineCategory.METRIC,
        minutes=-10,
        title="error_rate",
        metadata={
            "anomaly": True,
            "normalized_data": {"metric_name": "error_rate", "value": 0.9},
        },
    )
    error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="database timeout",
        metadata={"service_id": 1},
    )
    return TimelineResult(
        incident_id=42,
        project_id=7,
        started_at=_ts(0),
        ended_at=None,
        window_start=_ts(-60),
        window_end=_ts(60),
        entries=[deployment, anomaly, error],
        markers=TimelineMarkers(
            recent_deployment=deployment,
            first_anomaly=anomaly,
            first_relevant_error=error,
        ),
        counts={"deployment": 1, "metric": 1, "error": 1},
        correlations=[
            TemporalCorrelation(
                kind=CorrelationKind.DEPLOYMENT_TO_ERROR,
                source=deployment,
                target=error,
                time_difference=timedelta(minutes=30),
                correlation_score=0.9,
                reason="Deployment preceded error",
            ),
            TemporalCorrelation(
                kind=CorrelationKind.METRIC_ANOMALY_TO_ERROR,
                source=anomaly,
                target=error,
                time_difference=timedelta(minutes=10),
                correlation_score=0.88,
                reason="Metric anomaly preceded error",
            ),
        ],
        deployment_correlation=DeploymentCorrelationAssessment(
            is_related=True,
            relationship_score=0.85,
            deployment=deployment,
            supporting_evidence=[
                DeploymentEvidence(
                    kind=DeploymentEvidenceKind.DEPLOYMENT_BEFORE_FIRST_ERROR,
                    detail="Deployment preceded first error",
                    weight=0.35,
                )
            ],
            contradicting_evidence=[],
            summary="Strong deployment association",
        ),
        service_correlation=ServiceCorrelationResult(
            relationships=[
                ScoredServiceRelationship(
                    kind=ServiceRelationshipKind.ERROR_TO_SERVICE,
                    source_id="error_group:1",
                    source_label="database timeout",
                    target_id="service:1",
                    target_label="payments-api",
                    correlation_score=0.85,
                    evidence=[
                        ServiceRelationshipEvidence(
                            signal=ServiceRelationshipSignal.SERVICE_ATTRIBUTION,
                            detail="Error attributed to payments-api",
                            weight=0.4,
                        )
                    ],
                    reason="Error attributed to payments-api",
                    source_entry_id="error_group:1",
                    target_entry_id="error_group:1",
                )
            ],
            services=["payments-api"],
        ),
    )


def _medium_quality_timeline() -> TimelineResult:
    error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="timeout",
        metadata={"service_id": 2},
    )
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-5,
        title="v1.0.1",
    )
    return TimelineResult(
        incident_id=1,
        project_id=1,
        started_at=_ts(0),
        ended_at=None,
        window_start=_ts(-30),
        window_end=_ts(30),
        entries=[deployment, error],
        markers=TimelineMarkers(
            recent_deployment=deployment,
            first_relevant_error=error,
        ),
        counts={"deployment": 1, "error": 1},
        correlations=[
            TemporalCorrelation(
                kind=CorrelationKind.DEPLOYMENT_TO_ERROR,
                source=deployment,
                target=error,
                time_difference=timedelta(minutes=5),
                correlation_score=0.45,
                reason="Weak deployment link",
            ),
        ],
        deployment_correlation=DeploymentCorrelationAssessment(
            is_related=False,
            relationship_score=0.35,
            deployment=deployment,
            supporting_evidence=[
                DeploymentEvidence(
                    kind=DeploymentEvidenceKind.RECENT_DEPLOYMENT,
                    detail="Recent deployment observed",
                    weight=0.2,
                )
            ],
            contradicting_evidence=[
                DeploymentEvidence(
                    kind=DeploymentEvidenceKind.DEPLOYMENT_ALONE_INSUFFICIENT,
                    detail="Deployment alone is insufficient",
                    weight=0.3,
                )
            ],
            summary="Uncertain deployment association",
        ),
    )


def _low_quality_package() -> EvidenceGroup:
    return EvidenceGroup(
        incident_id=1,
        project_id=1,
        built_at=_ts(0),
        summary="Sparse evidence",
        evidence=[
            Evidence(
                key="marker-1",
                source=EvidenceSource.TIMELINE_MARKER,
                timestamp=_ts(0),
                event_reference=EventReference(timeline_entry_id="event:1"),
                description="Timeline marker identified: first_relevant_error",
                confidence=0.7,
                supporting_or_contradicting=EvidenceStance.NEUTRAL,
            ),
        ],
        relations=[],
        evidence_graph=None,
    )


def test_high_quality_evidence_scores_above_threshold() -> None:
    package = build_evidence_group(
        _high_quality_timeline(),
        built_at=_ts(0),
        service_names={1: "payments-api"},
    )

    assert package.quality is not None
    assert isinstance(package.quality, EvidenceQualityAssessment)
    assert package.quality.score >= 75
    assert package.quality.breakdown.source_diversity >= 60.0
    assert package.quality.breakdown.temporal_consistency == 100.0
    assert package.quality.breakdown.completeness >= 80.0
    assert package.quality.breakdown.consistency == 100.0
    assert "High evidence quality" in package.quality.summary


def test_medium_quality_evidence_scores_in_mid_range() -> None:
    package = build_evidence_group(
        _medium_quality_timeline(),
        built_at=_ts(0),
        service_names={2: "auth-service"},
        affected_service="auth-service",
    )

    assert package.quality is not None
    assert 45 <= package.quality.score < 75
    assert package.quality.breakdown.completeness < 80.0
    assert package.quality.breakdown.consistency < 100.0
    assert "Medium evidence quality" in package.quality.summary


def test_low_quality_evidence_scores_below_threshold() -> None:
    assessment = score_evidence_quality(_low_quality_package())

    assert assessment.score < 45
    assert assessment.breakdown.source_diversity == 20.0
    assert assessment.breakdown.correlation_strength == 0.0
    assert assessment.breakdown.completeness < 30.0
    assert "Low evidence quality" in assessment.summary


def test_score_evidence_quality_returns_all_breakdown_dimensions() -> None:
    package = build_evidence_group(
        _high_quality_timeline(),
        built_at=_ts(0),
        service_names={1: "payments-api"},
    )
    assessment = score_evidence_quality(package)

    breakdown = assessment.breakdown
    assert 0.0 <= breakdown.source_diversity <= 100.0
    assert 0.0 <= breakdown.temporal_consistency <= 100.0
    assert 0.0 <= breakdown.correlation_strength <= 100.0
    assert 0.0 <= breakdown.completeness <= 100.0
    assert 0.0 <= breakdown.consistency <= 100.0
    assert 0 <= assessment.score <= 100


def test_consistency_penalizes_contradicting_relations() -> None:
    package = EvidenceGroup(
        incident_id=1,
        project_id=1,
        built_at=_ts(0),
        evidence=[
            Evidence(
                key="support",
                source=EvidenceSource.DEPLOYMENT_CORRELATION,
                timestamp=_ts(0),
                description="supports",
                confidence=0.8,
                supporting_or_contradicting=EvidenceStance.SUPPORTING,
            ),
            Evidence(
                key="contradict",
                source=EvidenceSource.DEPLOYMENT_CORRELATION,
                timestamp=_ts(0),
                description="contradicts",
                confidence=0.8,
                supporting_or_contradicting=EvidenceStance.CONTRADICTING,
            ),
        ],
        relations=[
            EvidenceRelation(
                key="rel-1",
                source_evidence_key="support",
                target_evidence_key="contradict",
                kind=EvidenceRelationKind.CONTRADICTS,
                confidence=0.5,
                description="Mixed signals",
            )
        ],
    )

    assessment = score_evidence_quality(package)
    assert assessment.breakdown.consistency < 60.0


def test_source_diversity_rewards_multiple_evidence_sources() -> None:
    package = EvidenceGroup(
        incident_id=1,
        project_id=1,
        built_at=_ts(0),
        evidence=[
            Evidence(
                key=f"ev-{index}",
                source=source,
                timestamp=_ts(index),
                description="item",
                confidence=0.8,
                supporting_or_contradicting=EvidenceStance.SUPPORTING,
            )
            for index, source in enumerate(EvidenceSource)
        ],
    )

    assessment = score_evidence_quality(package)
    assert assessment.breakdown.source_diversity == 100.0
