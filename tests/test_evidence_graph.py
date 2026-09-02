"""Tests for the evidence graph builder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
    EvidenceGraphEdgeKind,
    EvidenceGraphNodeKind,
    build_evidence_graph,
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


def _full_chain_timeline() -> TimelineResult:
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


def test_build_evidence_graph_full_chain() -> None:
    graph = build_evidence_graph(
        _full_chain_timeline(),
        service_names={1: "payments-api"},
    )

    node_kinds = [node.kind for node in graph.nodes]
    assert node_kinds == [
        EvidenceGraphNodeKind.DEPLOYMENT,
        EvidenceGraphNodeKind.METRIC_ANOMALY,
        EvidenceGraphNodeKind.ERROR_INCREASE,
        EvidenceGraphNodeKind.SERVICE_FAILURE,
        EvidenceGraphNodeKind.INCIDENT,
    ]
    assert graph.chain == [
        "node:deployment",
        "node:metric-anomaly",
        "node:error-increase",
        "node:service-failure",
        "node:incident",
    ]
    assert graph.incident_id == 42
    assert graph.project_id == 7
    assert "node:deployment" in graph.summary
    assert "node:incident" in graph.summary

    chain_edges = [
        edge
        for edge in graph.edges
        if edge.kind is EvidenceGraphEdgeKind.LEADS_TO
    ]
    assert len(chain_edges) == 4
    assert chain_edges[0].source_id == "node:deployment"
    assert chain_edges[0].target_id == "node:metric-anomaly"
    assert chain_edges[-1].target_id == "node:incident"


def test_build_evidence_graph_uses_correlation_scores_for_chain_edges() -> None:
    graph = build_evidence_graph(
        _full_chain_timeline(),
        service_names={1: "payments-api"},
    )

    anomaly_to_error = next(
        edge
        for edge in graph.edges
        if edge.source_id == "node:metric-anomaly"
        and edge.target_id == "node:error-increase"
        and edge.kind is EvidenceGraphEdgeKind.LEADS_TO
    )
    assert anomaly_to_error.confidence == pytest.approx(0.85)


def test_build_evidence_graph_adds_escalated_to_for_deployment_correlation() -> None:
    graph = build_evidence_graph(
        _full_chain_timeline(),
        service_names={1: "payments-api"},
    )

    escalated = [
        edge
        for edge in graph.edges
        if edge.kind is EvidenceGraphEdgeKind.ESCALATED_TO
    ]
    assert len(escalated) == 1
    assert escalated[0].source_id == "node:deployment"
    assert escalated[0].target_id == "node:error-increase"
    assert escalated[0].confidence == pytest.approx(0.75)


def test_build_evidence_graph_partial_chain_without_deployment() -> None:
    error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="timeout",
        metadata={"service_id": 2},
    )
    timeline = TimelineResult(
        incident_id=1,
        project_id=1,
        started_at=_ts(0),
        ended_at=None,
        window_start=_ts(-30),
        window_end=_ts(30),
        entries=[error],
        markers=TimelineMarkers(first_relevant_error=error),
        counts={"error": 1},
        correlations=[],
    )

    graph = build_evidence_graph(
        timeline,
        service_names={2: "auth-service"},
    )

    assert [node.kind for node in graph.nodes] == [
        EvidenceGraphNodeKind.ERROR_INCREASE,
        EvidenceGraphNodeKind.SERVICE_FAILURE,
        EvidenceGraphNodeKind.INCIDENT,
    ]
    assert graph.chain == [
        "node:error-increase",
        "node:service-failure",
        "node:incident",
    ]


def test_build_evidence_graph_uses_affected_service_fallback() -> None:
    error = _entry(
        "error_group:1",
        TimelineCategory.ERROR,
        minutes=0,
        title="timeout",
    )
    timeline = TimelineResult(
        incident_id=1,
        project_id=1,
        started_at=_ts(0),
        ended_at=None,
        window_start=_ts(-30),
        window_end=_ts(30),
        entries=[error],
        markers=TimelineMarkers(first_relevant_error=error),
        counts={"error": 1},
        correlations=[],
    )

    graph = build_evidence_graph(timeline, affected_service="checkout-api")

    service_node = next(
        node
        for node in graph.nodes
        if node.kind is EvidenceGraphNodeKind.SERVICE_FAILURE
    )
    assert service_node.label == "Service failure: checkout-api"


def test_build_evidence_graph_empty_when_only_incident_context() -> None:
    timeline = TimelineResult(
        incident_id=1,
        project_id=1,
        started_at=_ts(0),
        ended_at=None,
        window_start=_ts(-30),
        window_end=_ts(30),
        entries=[],
        markers=TimelineMarkers(),
        counts={},
        correlations=[],
    )

    graph = build_evidence_graph(timeline)

    assert len(graph.nodes) == 1
    assert graph.nodes[0].kind is EvidenceGraphNodeKind.INCIDENT
    assert graph.chain == ["node:incident"]
    assert graph.edges == []


def test_build_evidence_group_attaches_graph() -> None:
    package = build_evidence_group(
        _full_chain_timeline(),
        built_at=_ts(0),
        service_names={1: "payments-api"},
    )

    assert package.evidence_graph is not None
    assert len(package.evidence_graph.nodes) == 5
    assert package.metadata["graph_node_count"] == 5
    assert package.metadata["graph_edge_count"] >= 4
