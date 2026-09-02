"""Tests for service and metric/error correlation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models.enums import Severity
from app.domain.correlation import (
    ServiceCorrelationThresholds,
    ServiceDependencyEdge,
    ServiceRelationshipKind,
    ServiceRelationshipSignal,
    correlate_service_metric_error,
    infer_dependencies_from_traces,
)
from app.domain.timeline.types import TimelineCategory, TimelineEntry


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


SERVICE_NAMES = {
    1: "payments-api",
    2: "auth-service",
    3: "inventory-service",
}


def test_metric_anomaly_to_error_on_same_service() -> None:
    entries = [
        _entry(
            "event:1",
            TimelineCategory.METRIC,
            minutes=0,
            title="error_rate",
            metadata={
                "service_id": 1,
                "anomaly": True,
                "normalized_data": {"metric_name": "error_rate", "value": 0.9},
            },
        ),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=5,
            title="checkout failed",
            metadata={"service_id": 1},
        ),
    ]

    result = correlate_service_metric_error(
        entries,
        service_names=SERVICE_NAMES,
    )

    relationship = next(
        item
        for item in result.relationships
        if item.kind is ServiceRelationshipKind.METRIC_ANOMALY_TO_ERROR
    )
    assert relationship.correlation_score >= 0.2
    signals = {item.signal for item in relationship.evidence}
    assert ServiceRelationshipSignal.TEMPORAL_PROXIMITY in signals
    assert ServiceRelationshipSignal.SAME_SERVICE in signals


def test_error_to_service_attribution() -> None:
    entries = [
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=0,
            title="database timeout",
            metadata={"service_id": 1},
        ),
    ]

    result = correlate_service_metric_error(entries, service_names=SERVICE_NAMES)

    relationship = next(
        item
        for item in result.relationships
        if item.kind is ServiceRelationshipKind.ERROR_TO_SERVICE
    )
    assert relationship.target_label == "payments-api"
    assert relationship.correlation_score == 0.5


def test_trace_dependency_inference_and_upstream_propagation() -> None:
    entries = [
        _entry(
            "event:1",
            TimelineCategory.TRACE,
            minutes=0,
            title="checkout",
            metadata={
                "service_id": 1,
                "normalized_data": {
                    "trace_id": "trace-abc",
                    "span_id": "span-pay",
                    "parent_span_id": None,
                },
            },
        ),
        _entry(
            "event:2",
            TimelineCategory.TRACE,
            minutes=1,
            title="auth validate",
            metadata={
                "service_id": 2,
                "normalized_data": {
                    "trace_id": "trace-abc",
                    "span_id": "span-auth",
                    "parent_span_id": "span-pay",
                },
            },
        ),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=2,
            title="auth token expired",
            metadata={"service_id": 2},
        ),
        _entry(
            "error_group:2",
            TimelineCategory.ERROR,
            minutes=4,
            title="checkout unauthorized",
            metadata={"service_id": 1},
        ),
    ]

    dependencies = infer_dependencies_from_traces(entries, service_names=SERVICE_NAMES)
    assert ServiceDependencyEdge(
        source_service="payments-api",
        target_service="auth-service",
        inferred_from="trace",
    ) in dependencies

    result = correlate_service_metric_error(
        entries,
        service_names=SERVICE_NAMES,
        explicit_dependencies=dependencies,
    )

    propagation = next(
        item
        for item in result.relationships
        if item.kind is ServiceRelationshipKind.UPSTREAM_ERROR_PROPAGATION
    )
    assert propagation.source_label == "auth token expired"
    assert propagation.target_label == "checkout unauthorized"
    assert propagation.correlation_score >= 0.2


def test_shared_trace_links_trace_to_error() -> None:
    entries = [
        _entry(
            "event:1",
            TimelineCategory.TRACE,
            minutes=0,
            title="checkout",
            metadata={
                "service_id": 1,
                "normalized_data": {
                    "trace_id": "trace-xyz",
                    "span_id": "span-1",
                },
            },
        ),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=1,
            title="timeout during checkout",
            metadata={
                "service_id": 1,
                "normalized_data": {"trace_id": "trace-xyz"},
            },
        ),
    ]

    result = correlate_service_metric_error(entries, service_names=SERVICE_NAMES)
    relationship = next(
        item
        for item in result.relationships
        if item.kind is ServiceRelationshipKind.TRACE_TO_ERROR
    )

    assert relationship.correlation_score >= 0.2
    assert any(
        item.signal is ServiceRelationshipSignal.SHARED_TRACE
        for item in relationship.evidence
    )


def test_cross_service_metric_anomaly_and_downstream_error_with_dependency() -> None:
    entries = [
        _entry(
            "event:1",
            TimelineCategory.METRIC,
            minutes=0,
            title="latency_ms",
            metadata={
                "service_id": 2,
                "anomaly": True,
                "normalized_data": {"metric_name": "latency_ms", "value": 900},
            },
        ),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=6,
            title="checkout timeout",
            metadata={"service_id": 1},
        ),
    ]
    dependencies = [
        ServiceDependencyEdge(
            source_service="payments-api",
            target_service="auth-service",
            inferred_from="explicit",
        )
    ]

    result = correlate_service_metric_error(
        entries,
        service_names=SERVICE_NAMES,
        explicit_dependencies=dependencies,
    )

    kinds = {item.kind for item in result.relationships}
    assert ServiceRelationshipKind.METRIC_ANOMALY_TO_SERVICE in kinds
    assert ServiceRelationshipKind.SERVICE_DEPENDENCY in kinds
    assert ServiceRelationshipKind.ERROR_TO_SERVICE in kinds


def test_relationships_below_min_score_are_filtered() -> None:
    entries = [
        _entry(
            "event:1",
            TimelineCategory.METRIC,
            minutes=0,
            title="cpu",
            metadata={
                "service_id": 1,
                "anomaly": True,
                "normalized_data": {"metric_name": "cpu", "value": 99},
            },
        ),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=60,
            title="late failure",
            metadata={"service_id": 1},
        ),
    ]

    result = correlate_service_metric_error(
        entries,
        service_names=SERVICE_NAMES,
        thresholds=ServiceCorrelationThresholds(
            metric_anomaly_to_error_max_lag=timedelta(minutes=10),
            min_score=0.8,
        ),
    )

    assert not any(
        item.kind is ServiceRelationshipKind.METRIC_ANOMALY_TO_ERROR
        for item in result.relationships
    )


def test_service_correlation_lists_involved_services() -> None:
    entries = [
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=0,
            title="inventory unavailable",
            metadata={"service_id": 3},
        ),
        _entry(
            "error_group:2",
            TimelineCategory.ERROR,
            minutes=2,
            title="checkout failed",
            metadata={"service_id": 1},
        ),
    ]

    result = correlate_service_metric_error(entries, service_names=SERVICE_NAMES)

    assert "payments-api" in result.services
    assert "inventory-service" in result.services
