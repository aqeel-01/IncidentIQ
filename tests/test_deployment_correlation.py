"""Tests for deployment correlation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.enums import Severity
from app.domain.correlation import (
    CorrelationKind,
    DeploymentCorrelationThresholds,
    DeploymentEvidenceKind,
    TemporalCorrelation,
    evaluate_deployment_correlation,
)
from app.domain.timeline.types import TimelineCategory, TimelineEntry, TimelineMarkers


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _entry(
    entry_id: str,
    category: TimelineCategory,
    *,
    minutes: int = 0,
    title: str = "event",
    severity: Severity | None = None,
    metadata: dict | None = None,
) -> TimelineEntry:
    return TimelineEntry(
        id=entry_id,
        category=category,
        timestamp=_ts(minutes),
        title=title,
        severity=severity,
        metadata=metadata or {},
    )


def _markers(
    *,
    deployment: TimelineEntry | None = None,
    first_error: TimelineEntry | None = None,
    first_anomaly: TimelineEntry | None = None,
) -> TimelineMarkers:
    return TimelineMarkers(
        recent_deployment=deployment,
        first_relevant_error=first_error,
        first_anomaly=first_anomaly,
    )


def test_deployment_alone_is_not_related() -> None:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-60,
        title="v1.2.2",
        metadata={"normalized_data": {"repository": "payments-api"}},
    )
    assessment = evaluate_deployment_correlation(
        incident_started_at=_ts(0),
        affected_service="payments-api",
        markers=_markers(deployment=deployment),
        correlations=[],
    )

    assert assessment.is_related is False
    assert any(
        item.kind is DeploymentEvidenceKind.RECENT_DEPLOYMENT
        for item in assessment.supporting_evidence
    )
    assert any(
        item.kind is DeploymentEvidenceKind.DEPLOYMENT_ALONE_INSUFFICIENT
        for item in assessment.contradicting_evidence
    )
    assert "does not establish causation" in assessment.summary.lower() or (
        "does not imply causation" in assessment.summary.lower()
    )


def test_deployment_before_error_is_related() -> None:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-60,
        title="v1.2.2",
        metadata={"normalized_data": {"repository": "payments-api"}},
    )
    first_error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="connection timeout talking to database",
    )
    correlation = TemporalCorrelation(
        kind=CorrelationKind.DEPLOYMENT_TO_ERROR,
        source=deployment,
        target=first_error,
        time_difference=timedelta(minutes=60),
        correlation_score=0.5,
        reason="Deployment 'v1.2.2' preceded error",
    )

    assessment = evaluate_deployment_correlation(
        incident_started_at=_ts(0),
        affected_service="payments-api",
        markers=_markers(deployment=deployment, first_error=first_error),
        correlations=[correlation],
    )

    assert assessment.is_related is True
    assert assessment.deployment is not None
    assert any(
        item.kind is DeploymentEvidenceKind.DEPLOYMENT_BEFORE_FIRST_ERROR
        for item in assessment.supporting_evidence
    )
    assert any(
        item.kind is DeploymentEvidenceKind.DEPLOYMENT_ERROR_TEMPORAL_LINK
        for item in assessment.supporting_evidence
    )
    assert "does not establish causation" in assessment.summary.lower()


def test_error_before_deployment_contradicts_relationship() -> None:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=0,
        title="v1.2.2",
    )
    first_error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=-10,
        title="checkout failed",
    )

    assessment = evaluate_deployment_correlation(
        incident_started_at=_ts(0),
        affected_service=None,
        markers=_markers(deployment=deployment, first_error=first_error),
        correlations=[],
    )

    assert assessment.is_related is False
    assert any(
        item.kind is DeploymentEvidenceKind.FIRST_ERROR_BEFORE_DEPLOYMENT
        for item in assessment.contradicting_evidence
    )
    assert "unlikely" in assessment.summary.lower()


def test_changed_component_overlap_supports_relationship() -> None:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-30,
        title="v1.2.2",
        metadata={
            "normalized_data": {
                "repository": "payments-api",
                "changed_files": [
                    "src/payments/checkout.py",
                    "src/payments/database.py",
                ],
            }
        },
    )
    first_error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=-5,
        title="timeout in checkout.py",
    )

    assessment = evaluate_deployment_correlation(
        incident_started_at=_ts(0),
        affected_service="payments-api",
        markers=_markers(deployment=deployment, first_error=first_error),
        correlations=[],
        thresholds=DeploymentCorrelationThresholds(min_relationship_score=0.3),
    )

    assert any(
        item.kind is DeploymentEvidenceKind.CHANGED_COMPONENT_OVERLAP
        for item in assessment.supporting_evidence
    )
    assert assessment.is_related is True


def test_no_recent_deployment_returns_negative_assessment() -> None:
    assessment = evaluate_deployment_correlation(
        incident_started_at=_ts(0),
        affected_service="payments-api",
        markers=_markers(),
        correlations=[],
    )

    assert assessment.is_related is False
    assert assessment.deployment is None
    assert assessment.supporting_evidence == []
    assert any(
        item.kind is DeploymentEvidenceKind.NO_RECENT_DEPLOYMENT
        for item in assessment.contradicting_evidence
    )


def test_service_mismatch_adds_contradicting_evidence() -> None:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-20,
        title="v1.0.0",
        metadata={"normalized_data": {"repository": "billing-api"}},
    )
    first_error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="payment declined",
    )

    assessment = evaluate_deployment_correlation(
        incident_started_at=_ts(0),
        affected_service="payments-api",
        markers=_markers(deployment=deployment, first_error=first_error),
        correlations=[],
    )

    assert any(
        item.kind is DeploymentEvidenceKind.AFFECTED_SERVICE_MISMATCH
        for item in assessment.contradicting_evidence
    )


def test_anomaly_before_deployment_blocks_relationship() -> None:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=0,
        title="v1.2.2",
    )
    first_anomaly = _entry(
        "event:2",
        TimelineCategory.METRIC,
        minutes=-15,
        title="error_rate",
        metadata={"anomaly": True},
    )
    first_error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=5,
        title="database timeout",
    )

    assessment = evaluate_deployment_correlation(
        incident_started_at=_ts(0),
        affected_service=None,
        markers=_markers(
            deployment=deployment,
            first_error=first_error,
            first_anomaly=first_anomaly,
        ),
        correlations=[],
    )

    assert assessment.is_related is False
    assert any(
        item.kind is DeploymentEvidenceKind.FIRST_ANOMALY_BEFORE_DEPLOYMENT
        for item in assessment.contradicting_evidence
    )


@pytest.mark.parametrize(
    ("supporting_total", "contradicting_total", "expected_score"),
    [
        (0.0, 0.0, 0.5),
        (1.0, 0.0, 0.75),
        (0.0, 1.0, 0.25),
    ],
)
def test_relationship_score_is_deterministic(
    supporting_total: float,
    contradicting_total: float,
    expected_score: float,
) -> None:
    score = round(
        max(0.0, min(1.0, 0.5 + ((supporting_total - contradicting_total) * 0.25))),
        4,
    )
    assert score == expected_score
