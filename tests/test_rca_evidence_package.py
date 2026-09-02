"""Tests for the RCA evidence package builder."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from app.domain.evidence import build_evidence_group
from app.domain.rca import (
    RCAHistoricalContext,
    RCAIncidentContext,
    build_rca_evidence_package,
    package_to_canonical_json,
)
from app.domain.timeline.types import (
    TimelineCategory,
    TimelineEntry,
    TimelineMarkers,
    TimelineResult,
)

SNAPSHOT_PATH = (
    Path(__file__).parent / "fixtures" / "rca_evidence_package_full.json"
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


def _investigation_timeline() -> TimelineResult:
    deployment = _entry(
        "event:1",
        TimelineCategory.DEPLOYMENT,
        minutes=-30,
        title="v1.2.2",
        metadata={
            "service_id": 1,
            "normalized_data": {"version": "v1.2.2"},
        },
    )
    anomaly = _entry(
        "event:2",
        TimelineCategory.METRIC,
        minutes=-10,
        title="error_rate",
        metadata={
            "anomaly": True,
            "service_id": 1,
            "normalized_data": {"metric_name": "error_rate", "value": 0.9},
        },
    )
    error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="database timeout",
        metadata={"service_id": 1, "occurrence_count": 12},
    )
    alert = _entry(
        "event:3",
        TimelineCategory.ALERT,
        minutes=5,
        title="HighErrorRate",
        metadata={"service_id": 1},
    )
    log = _entry(
        "event:4",
        TimelineCategory.LOG,
        minutes=1,
        title="connection timeout talking to database",
        metadata={"service_id": 1},
    )
    timeline = TimelineResult(
        incident_id=42,
        project_id=7,
        started_at=_ts(0),
        ended_at=None,
        window_start=_ts(-60),
        window_end=_ts(60),
        entries=[deployment, anomaly, error, alert, log],
        markers=TimelineMarkers(
            recent_deployment=deployment,
            first_anomaly=anomaly,
            first_relevant_error=error,
            first_alert=alert,
        ),
        counts={
            "deployment": 1,
            "metric": 1,
            "error": 1,
            "alert": 1,
            "log": 1,
        },
        correlations=[
            TemporalCorrelation(
                kind=CorrelationKind.DEPLOYMENT_TO_ERROR,
                source=deployment,
                target=error,
                time_difference=timedelta(minutes=30),
                correlation_score=0.75,
                reason="Deployment preceded error",
            ),
            TemporalCorrelation(
                kind=CorrelationKind.METRIC_ANOMALY_TO_ERROR,
                source=anomaly,
                target=error,
                time_difference=timedelta(minutes=10),
                correlation_score=0.85,
                reason="Metric anomaly preceded error",
            ),
        ],
        deployment_correlation=DeploymentCorrelationAssessment(
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
            contradicting_evidence=[],
            summary="Possible deployment association",
        ),
        service_correlation=ServiceCorrelationResult(
            relationships=[
                ScoredServiceRelationship(
                    kind=ServiceRelationshipKind.ERROR_TO_SERVICE,
                    source_id="error_group:1",
                    source_label="database timeout",
                    target_id="service:1",
                    target_label="payments-api",
                    correlation_score=0.8,
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
    evidence_group = build_evidence_group(
        timeline,
        built_at=_ts(0),
        service_names={1: "payments-api"},
    )
    return timeline.model_copy(update={"evidence_group": evidence_group})


def _incident_context() -> RCAIncidentContext:
    return RCAIncidentContext(
        incident_id=42,
        project_id=7,
        title="Checkout failures",
        environment="production",
        severity="high",
        status="open",
        service="payments-api",
        started_at=_ts(0),
        ended_at=None,
        occurrence_count=3,
    )


def test_build_rca_evidence_package_is_deterministic() -> None:
    timeline = _investigation_timeline()
    incident = _incident_context()

    first = package_to_canonical_json(
        build_rca_evidence_package(
            incident=incident,
            timeline=timeline,
            service_names={1: "payments-api"},
        )
    )
    second = package_to_canonical_json(
        build_rca_evidence_package(
            incident=incident,
            timeline=timeline,
            service_names={1: "payments-api"},
        )
    )

    assert first == second


def test_build_rca_evidence_package_excludes_raw_metadata() -> None:
    package = build_rca_evidence_package(
        incident=_incident_context(),
        timeline=_investigation_timeline(),
        service_names={1: "payments-api"},
    )
    payload = package_to_canonical_json(package)

    assert "raw_data" not in payload
    assert "fingerprint" not in payload
    assert "source_type" not in payload


def test_build_rca_evidence_package_includes_required_sections() -> None:
    package = build_rca_evidence_package(
        incident=_incident_context(),
        timeline=_investigation_timeline(),
        service_names={1: "payments-api"},
        historical_context=RCAHistoricalContext(
            prior_incident_count=2,
            related_incident_ids=[11, 19],
            notes=["Similar checkout outage last week"],
        ),
    )

    assert package.incident.title == "Checkout failures"
    assert package.symptoms
    assert package.error_groups
    assert package.anomalies
    assert package.deployments
    assert package.timeline
    assert package.correlations
    assert package.evidence_graph is not None
    assert package.evidence_quality is not None
    assert package.historical_context is not None
    assert package.historical_context.related_incident_ids == [11, 19]


def test_build_rca_evidence_package_snapshot() -> None:
    package = build_rca_evidence_package(
        incident=_incident_context(),
        timeline=_investigation_timeline(),
        service_names={1: "payments-api"},
    )
    actual = package_to_canonical_json(package)
    expected = SNAPSHOT_PATH.read_text(encoding="utf-8")

    assert json.loads(actual) == json.loads(expected)


def test_build_rca_evidence_package_without_historical_context() -> None:
    package = build_rca_evidence_package(
        incident=_incident_context(),
        timeline=_investigation_timeline(),
        service_names={1: "payments-api"},
    )

    assert package.historical_context is None
