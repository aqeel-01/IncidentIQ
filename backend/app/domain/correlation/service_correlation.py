"""Service, metric, and error correlation engine."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from app.domain.correlation.engine import (
    correlation_score,
    is_error_entry,
    is_metric_anomaly_entry,
)
from app.domain.correlation.types import (
    ScoredServiceRelationship,
    ServiceCorrelationResult,
    ServiceCorrelationThresholds,
    ServiceDependencyEdge,
    ServiceRelationshipEvidence,
    ServiceRelationshipKind,
    ServiceRelationshipSignal,
)
from app.domain.timeline.types import TimelineCategory, TimelineEntry


@dataclass(frozen=True, slots=True)
class _SpanInfo:
    service: str
    span_id: str | None
    parent_span_id: str | None
    timestamp: object
    entry_id: str


def correlate_service_metric_error(
    entries: Sequence[TimelineEntry],
    *,
    service_names: dict[int, str],
    explicit_dependencies: Sequence[ServiceDependencyEdge] | None = None,
    thresholds: ServiceCorrelationThresholds | None = None,
) -> ServiceCorrelationResult:
    """Correlate metric anomalies, errors, services, dependencies, and traces."""

    config = thresholds or ServiceCorrelationThresholds()
    dependencies = list(explicit_dependencies or [])
    dependencies.extend(
        infer_dependencies_from_traces(entries, service_names=service_names)
    )
    dependencies = _dedupe_dependencies(dependencies)

    relationships: list[ScoredServiceRelationship] = []
    relationships.extend(
        _correlate_metric_anomalies_to_errors(entries, config=config)
    )
    relationships.extend(
        _correlate_metric_anomalies_to_services(
            entries,
            service_names=service_names,
            config=config,
        )
    )
    relationships.extend(
        _correlate_errors_to_services(entries, service_names=service_names)
    )
    relationships.extend(
        _correlate_traces_to_errors(
            entries,
            service_names=service_names,
            config=config,
        )
    )
    relationships.extend(_correlate_service_dependencies(dependencies))
    relationships.extend(
        _correlate_upstream_error_propagation(
            entries,
            dependencies=dependencies,
            service_names=service_names,
            config=config,
        )
    )

    filtered = [
        relationship
        for relationship in relationships
        if relationship.correlation_score >= config.min_score
    ]
    filtered.sort(
        key=lambda item: (
            -item.correlation_score,
            item.kind.value,
            item.source_id,
            item.target_id,
        )
    )

    services = sorted(
        {
            name
            for name in service_names.values()
            if _service_present(name, entries, service_names)
        }
    )

    return ServiceCorrelationResult(
        relationships=filtered,
        dependencies=dependencies,
        services=services,
    )


def infer_dependencies_from_traces(
    entries: Sequence[TimelineEntry],
    *,
    service_names: dict[int, str],
) -> list[ServiceDependencyEdge]:
    """Infer service dependencies from shared traces and span hierarchy."""

    spans_by_trace: dict[str, list[_SpanInfo]] = defaultdict(list)
    for entry in entries:
        if entry.category not in {TimelineCategory.TRACE, TimelineCategory.LOG}:
            continue

        normalized = entry.metadata.get("normalized_data", {})
        trace_id = normalized.get("trace_id")
        if not trace_id:
            continue

        service = _entry_service_name(entry, service_names)
        if service is None:
            continue

        spans_by_trace[str(trace_id)].append(
            _SpanInfo(
                service=service,
                span_id=_optional_str(normalized.get("span_id")),
                parent_span_id=_optional_str(normalized.get("parent_span_id")),
                timestamp=entry.timestamp,
                entry_id=entry.id,
            )
        )

    edges: set[tuple[str, str]] = set()
    for spans in spans_by_trace.values():
        span_by_id = {span.span_id: span for span in spans if span.span_id}
        for span in spans:
            if span.parent_span_id and span.parent_span_id in span_by_id:
                parent = span_by_id[span.parent_span_id]
                if parent.service != span.service:
                    edges.add((parent.service, span.service))

        ordered_services: list[str] = []
        seen: set[str] = set()
        for span in sorted(spans, key=lambda item: item.timestamp):
            if span.service in seen:
                continue
            ordered_services.append(span.service)
            seen.add(span.service)
        for index in range(len(ordered_services) - 1):
            edges.add((ordered_services[index], ordered_services[index + 1]))

    return [
        ServiceDependencyEdge(
            source_service=source,
            target_service=target,
            inferred_from="trace",
        )
        for source, target in sorted(edges)
    ]


def _correlate_metric_anomalies_to_errors(
    entries: Sequence[TimelineEntry],
    *,
    config: ServiceCorrelationThresholds,
) -> list[ScoredServiceRelationship]:
    anomalies = [entry for entry in entries if is_metric_anomaly_entry(entry)]
    errors = [entry for entry in entries if is_error_entry(entry)]
    relationships: list[ScoredServiceRelationship] = []

    for anomaly in anomalies:
        match = _find_earliest_target(
            anomaly,
            errors,
            max_lag=config.metric_anomaly_to_error_max_lag,
        )
        if match is None:
            continue

        error, lag = match
        evidence = _build_temporal_evidence(
            lag=lag,
            max_lag=config.metric_anomaly_to_error_max_lag,
            temporal_weight=config.temporal_weight,
        )
        evidence.extend(
            _same_service_evidence(anomaly, error, weight=config.same_service_weight)
        )
        score = _score_evidence(evidence)
        relationships.append(
            ScoredServiceRelationship(
                kind=ServiceRelationshipKind.METRIC_ANOMALY_TO_ERROR,
                source_id=anomaly.id,
                source_label=anomaly.title,
                target_id=error.id,
                target_label=error.title,
                correlation_score=score,
                evidence=evidence,
                reason=(
                    f"Metric anomaly '{anomaly.title}' temporally aligns with "
                    f"error '{error.title}'"
                ),
                source_entry_id=anomaly.id,
                target_entry_id=error.id,
            )
        )

    return relationships


def _correlate_metric_anomalies_to_services(
    entries: Sequence[TimelineEntry],
    *,
    service_names: dict[int, str],
    config: ServiceCorrelationThresholds,
) -> list[ScoredServiceRelationship]:
    relationships: list[ScoredServiceRelationship] = []
    for anomaly in (entry for entry in entries if is_metric_anomaly_entry(entry)):
        service_name = _entry_service_name(anomaly, service_names)
        if service_name is None:
            continue

        evidence = [
            ServiceRelationshipEvidence(
                signal=ServiceRelationshipSignal.SERVICE_ATTRIBUTION,
                detail=f"Metric anomaly attributed to service '{service_name}'",
                weight=config.same_service_weight,
            )
        ]
        relationships.append(
            ScoredServiceRelationship(
                kind=ServiceRelationshipKind.METRIC_ANOMALY_TO_SERVICE,
                source_id=anomaly.id,
                source_label=anomaly.title,
                target_id=f"service:{service_name}",
                target_label=service_name,
                correlation_score=_score_evidence(evidence),
                evidence=evidence,
                reason=(
                    f"Metric anomaly '{anomaly.title}' is attributed to service "
                    f"'{service_name}'"
                ),
                source_entry_id=anomaly.id,
            )
        )

    return relationships


def _correlate_errors_to_services(
    entries: Sequence[TimelineEntry],
    *,
    service_names: dict[int, str],
) -> list[ScoredServiceRelationship]:
    relationships: list[ScoredServiceRelationship] = []
    for error in (entry for entry in entries if is_error_entry(entry)):
        service_name = _entry_service_name(error, service_names)
        if service_name is None:
            continue

        evidence = [
            ServiceRelationshipEvidence(
                signal=ServiceRelationshipSignal.SERVICE_ATTRIBUTION,
                detail=f"Error group attributed to service '{service_name}'",
                weight=0.5,
            )
        ]
        relationships.append(
            ScoredServiceRelationship(
                kind=ServiceRelationshipKind.ERROR_TO_SERVICE,
                source_id=error.id,
                source_label=error.title,
                target_id=f"service:{service_name}",
                target_label=service_name,
                correlation_score=_score_evidence(evidence),
                evidence=evidence,
                reason=(
                    f"Error '{error.title}' is attributed to service '{service_name}'"
                ),
                source_entry_id=error.id,
            )
        )

    return relationships


def _correlate_traces_to_errors(
    entries: Sequence[TimelineEntry],
    *,
    service_names: dict[int, str],
    config: ServiceCorrelationThresholds,
) -> list[ScoredServiceRelationship]:
    trace_entries = [
        entry
        for entry in entries
        if entry.category is TimelineCategory.TRACE
        or entry.metadata.get("normalized_data", {}).get("trace_id")
    ]
    errors = [entry for entry in entries if is_error_entry(entry)]
    relationships: list[ScoredServiceRelationship] = []

    for trace_entry in trace_entries:
        trace_id = trace_entry.metadata.get("normalized_data", {}).get("trace_id")
        if not trace_id:
            continue

        for error in errors:
            error_trace_id = error.metadata.get("normalized_data", {}).get("trace_id")
            if error_trace_id != trace_id:
                continue

            lag = abs(error.timestamp - trace_entry.timestamp)
            if lag > config.trace_to_error_max_lag:
                continue

            evidence = [
                ServiceRelationshipEvidence(
                    signal=ServiceRelationshipSignal.SHARED_TRACE,
                    detail=f"Shared trace_id '{trace_id}'",
                    weight=config.trace_weight,
                )
            ]
            evidence.extend(
                _build_temporal_evidence(
                    lag=lag,
                    max_lag=config.trace_to_error_max_lag,
                    temporal_weight=config.temporal_weight,
                )
            )
            evidence.extend(
                _same_service_evidence(
                    trace_entry,
                    error,
                    weight=config.same_service_weight,
                )
            )
            relationships.append(
                ScoredServiceRelationship(
                    kind=ServiceRelationshipKind.TRACE_TO_ERROR,
                    source_id=trace_entry.id,
                    source_label=trace_entry.title,
                    target_id=error.id,
                    target_label=error.title,
                    correlation_score=_score_evidence(evidence),
                    evidence=evidence,
                    reason=(
                        f"Trace '{trace_entry.title}' shares trace_id '{trace_id}' "
                        f"with error '{error.title}'"
                    ),
                    source_entry_id=trace_entry.id,
                    target_entry_id=error.id,
                )
            )

    return relationships


def _correlate_service_dependencies(
    dependencies: Sequence[ServiceDependencyEdge],
) -> list[ScoredServiceRelationship]:
    relationships: list[ScoredServiceRelationship] = []
    for edge in dependencies:
        evidence = [
            ServiceRelationshipEvidence(
                signal=ServiceRelationshipSignal.DEPENDENCY_EDGE,
                detail=(
                    f"Service '{edge.source_service}' depends on "
                    f"'{edge.target_service}'"
                ),
                weight=0.5,
            )
        ]
        relationships.append(
            ScoredServiceRelationship(
                kind=ServiceRelationshipKind.SERVICE_DEPENDENCY,
                source_id=f"service:{edge.source_service}",
                source_label=edge.source_service,
                target_id=f"service:{edge.target_service}",
                target_label=edge.target_service,
                correlation_score=_score_evidence(evidence),
                evidence=evidence,
                reason=(
                    f"Service '{edge.source_service}' depends on "
                    f"'{edge.target_service}' (inferred from {edge.inferred_from})"
                ),
            )
        )
    return relationships


def _correlate_upstream_error_propagation(
    entries: Sequence[TimelineEntry],
    *,
    dependencies: Sequence[ServiceDependencyEdge],
    service_names: dict[int, str],
    config: ServiceCorrelationThresholds,
) -> list[ScoredServiceRelationship]:
    errors_by_service: dict[str, list[TimelineEntry]] = defaultdict(list)
    for error in (entry for entry in entries if is_error_entry(entry)):
        service_name = _entry_service_name(error, service_names)
        if service_name is not None:
            errors_by_service[service_name].append(error)

    relationships: list[ScoredServiceRelationship] = []
    for edge in dependencies:
        upstream_errors = errors_by_service.get(edge.target_service, [])
        downstream_errors = errors_by_service.get(edge.source_service, [])
        if not upstream_errors or not downstream_errors:
            continue

        for upstream_error in upstream_errors:
            match = _find_earliest_target(
                upstream_error,
                downstream_errors,
                max_lag=config.upstream_propagation_max_lag,
            )
            if match is None:
                continue

            downstream_error, lag = match
            evidence = _build_temporal_evidence(
                lag=lag,
                max_lag=config.upstream_propagation_max_lag,
                temporal_weight=config.temporal_weight,
            )
            evidence.append(
                ServiceRelationshipEvidence(
                    signal=ServiceRelationshipSignal.DEPENDENCY_EDGE,
                    detail=(
                        f"Upstream service '{edge.target_service}' error preceded "
                        f"downstream service '{edge.source_service}' error"
                    ),
                    weight=config.dependency_weight,
                )
            )
            relationships.append(
                ScoredServiceRelationship(
                    kind=ServiceRelationshipKind.UPSTREAM_ERROR_PROPAGATION,
                    source_id=upstream_error.id,
                    source_label=upstream_error.title,
                    target_id=downstream_error.id,
                    target_label=downstream_error.title,
                    correlation_score=_score_evidence(evidence),
                    evidence=evidence,
                    reason=(
                        f"Upstream error on '{edge.target_service}' preceded "
                        f"downstream error on '{edge.source_service}'"
                    ),
                    source_entry_id=upstream_error.id,
                    target_entry_id=downstream_error.id,
                )
            )

    return relationships


def _build_temporal_evidence(
    *,
    lag: timedelta,
    max_lag: timedelta,
    temporal_weight: float,
) -> list[ServiceRelationshipEvidence]:
    temporal_score = correlation_score(lag, max_lag=max_lag)
    return [
        ServiceRelationshipEvidence(
            signal=ServiceRelationshipSignal.TEMPORAL_PROXIMITY,
            detail=(
                f"Events separated by {int(lag.total_seconds())} seconds "
                f"(temporal score {temporal_score:.2f})"
            ),
            weight=round(temporal_weight * temporal_score, 4),
        )
    ]


def _same_service_evidence(
    left: TimelineEntry,
    right: TimelineEntry,
    *,
    weight: float,
) -> list[ServiceRelationshipEvidence]:
    left_service_id = left.metadata.get("service_id")
    right_service_id = right.metadata.get("service_id")
    if left_service_id is None or right_service_id is None:
        return []
    if left_service_id != right_service_id:
        return []
    return [
        ServiceRelationshipEvidence(
            signal=ServiceRelationshipSignal.SAME_SERVICE,
            detail=f"Both events attributed to service_id {left_service_id}",
            weight=weight,
        )
    ]


def _score_evidence(evidence: Sequence[ServiceRelationshipEvidence]) -> float:
    return round(min(1.0, sum(item.weight for item in evidence)), 4)


def _find_earliest_target(
    source: TimelineEntry,
    targets: Sequence[TimelineEntry],
    *,
    max_lag: timedelta,
) -> tuple[TimelineEntry, timedelta] | None:
    best: tuple[TimelineEntry, timedelta] | None = None
    for target in targets:
        if target.id == source.id:
            continue
        lag = target.timestamp - source.timestamp
        if lag.total_seconds() < 0 or lag > max_lag:
            continue
        if best is None or lag < best[1]:
            best = (target, lag)
    return best


def _entry_service_name(
    entry: TimelineEntry,
    service_names: dict[int, str],
) -> str | None:
    service_id = entry.metadata.get("service_id")
    if service_id is None:
        return None
    return service_names.get(int(service_id))


def _service_present(
    service_name: str,
    entries: Sequence[TimelineEntry],
    service_names: dict[int, str],
) -> bool:
    matching_ids = {
        service_id
        for service_id, name in service_names.items()
        if name == service_name
    }
    return any(entry.metadata.get("service_id") in matching_ids for entry in entries)


def _dedupe_dependencies(
    dependencies: Sequence[ServiceDependencyEdge],
) -> list[ServiceDependencyEdge]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ServiceDependencyEdge] = []
    for edge in dependencies:
        key = (edge.source_service, edge.target_service, edge.inferred_from)
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    return unique


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
