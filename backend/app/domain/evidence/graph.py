"""Evidence graph construction from timeline and correlation results."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.correlation import is_metric_anomaly_entry
from app.domain.correlation.types import CorrelationKind
from app.domain.evidence.types import (
    EventReference,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphEdgeKind,
    EvidenceGraphNode,
    EvidenceGraphNodeKind,
)
from app.domain.timeline.types import TimelineCategory, TimelineEntry, TimelineResult

_CHAIN_ORDER = (
    EvidenceGraphNodeKind.DEPLOYMENT,
    EvidenceGraphNodeKind.METRIC_ANOMALY,
    EvidenceGraphNodeKind.ERROR_INCREASE,
    EvidenceGraphNodeKind.SERVICE_FAILURE,
    EvidenceGraphNodeKind.INCIDENT,
)


def build_evidence_graph(
    timeline: TimelineResult,
    *,
    service_names: dict[int, str] | None = None,
    affected_service: str | None = None,
) -> EvidenceGraph:
    """Combine timeline and correlation outputs into an evidence graph."""

    builder = _EvidenceGraphBuilder(
        timeline=timeline,
        service_names=service_names or {},
        affected_service=affected_service,
    )
    return builder.build()


class _EvidenceGraphBuilder:
    def __init__(
        self,
        *,
        timeline: TimelineResult,
        service_names: dict[int, str],
        affected_service: str | None,
    ) -> None:
        self._timeline = timeline
        self._service_names = service_names
        self._affected_service = affected_service
        self._nodes: dict[EvidenceGraphNodeKind, EvidenceGraphNode] = {}
        self._edges: list[EvidenceGraphEdge] = []
        self._edge_counter = 0

    def build(self) -> EvidenceGraph:
        self._add_deployment_node()
        self._add_metric_anomaly_node()
        self._add_error_increase_node()
        self._add_service_failure_node()
        self._add_incident_node()
        self._add_primary_chain_edges()
        self._add_correlation_edges()

        chain = [
            node.id
            for kind in _CHAIN_ORDER
            if (node := self._nodes.get(kind)) is not None
        ]
        nodes = [self._nodes[kind] for kind in _CHAIN_ORDER if kind in self._nodes]

        return EvidenceGraph(
            incident_id=self._timeline.incident_id,
            project_id=self._timeline.project_id,
            nodes=nodes,
            edges=self._edges,
            chain=chain,
            summary=_build_graph_summary(chain),
        )

    def _add_deployment_node(self) -> None:
        deployment = self._timeline.markers.recent_deployment
        if deployment is None:
            return

        confidence = 0.6
        assessment = self._timeline.deployment_correlation
        if assessment is not None:
            confidence = max(confidence, assessment.relationship_score)

        self._nodes[EvidenceGraphNodeKind.DEPLOYMENT] = _node_from_entry(
            node_id="node:deployment",
            kind=EvidenceGraphNodeKind.DEPLOYMENT,
            entry=deployment,
            label=f"Deployment: {deployment.title}",
            confidence=confidence,
            description="Recent deployment before incident start",
        )

    def _add_metric_anomaly_node(self) -> None:
        anomaly_entry = _first_metric_anomaly(self._timeline.entries)
        if anomaly_entry is None:
            anomaly_entry = self._timeline.markers.first_anomaly
        if anomaly_entry is None or not _is_metric_anomaly_candidate(anomaly_entry):
            return

        self._nodes[EvidenceGraphNodeKind.METRIC_ANOMALY] = _node_from_entry(
            node_id="node:metric-anomaly",
            kind=EvidenceGraphNodeKind.METRIC_ANOMALY,
            entry=anomaly_entry,
            label=f"Metric anomaly: {anomaly_entry.title}",
            confidence=0.8,
            description="Statistically anomalous metric observed before errors",
        )

    def _add_error_increase_node(self) -> None:
        error = self._timeline.markers.first_relevant_error
        if error is None:
            return

        confidence = 0.85
        for correlation in self._timeline.correlations:
            if correlation.target.id == error.id:
                confidence = max(confidence, correlation.correlation_score)

        self._nodes[EvidenceGraphNodeKind.ERROR_INCREASE] = _node_from_entry(
            node_id="node:error-increase",
            kind=EvidenceGraphNodeKind.ERROR_INCREASE,
            entry=error,
            label=f"Error increase: {error.title}",
            confidence=confidence,
            description="First relevant error observed during the incident window",
        )

    def _add_service_failure_node(self) -> None:
        error = self._timeline.markers.first_relevant_error
        service_name = self._resolve_service_name(error)
        if service_name is None and self._affected_service is not None:
            service_name = self._affected_service
        if service_name is None:
            return

        confidence = 0.7
        if self._timeline.service_correlation is not None:
            for relationship in self._timeline.service_correlation.relationships:
                if relationship.target_label == service_name:
                    confidence = max(confidence, relationship.correlation_score)

        timestamp = error.timestamp if error is not None else self._timeline.started_at
        self._nodes[EvidenceGraphNodeKind.SERVICE_FAILURE] = EvidenceGraphNode(
            id="node:service-failure",
            kind=EvidenceGraphNodeKind.SERVICE_FAILURE,
            label=f"Service failure: {service_name}",
            timestamp=timestamp,
            event_reference=EventReference(),
            confidence=confidence,
            description=(
                f"Errors and correlated signals attributed to service '{service_name}'"
            ),
        )

    def _add_incident_node(self) -> None:
        self._nodes[EvidenceGraphNodeKind.INCIDENT] = EvidenceGraphNode(
            id="node:incident",
            kind=EvidenceGraphNodeKind.INCIDENT,
            label=f"Incident {self._timeline.incident_id}",
            timestamp=self._timeline.started_at,
            event_reference=EventReference(),
            confidence=1.0,
            description="Tracked production incident under investigation",
        )

    def _add_primary_chain_edges(self) -> None:
        ordered_kinds = [kind for kind in _CHAIN_ORDER if kind in self._nodes]
        for index in range(len(ordered_kinds) - 1):
            source_kind = ordered_kinds[index]
            target_kind = ordered_kinds[index + 1]
            source = self._nodes[source_kind]
            target = self._nodes[target_kind]
            confidence = _chain_edge_confidence(
                source=source,
                target=target,
                correlations=self._timeline.correlations,
            )
            self._edges.append(
                EvidenceGraphEdge(
                    key=self._next_edge_key("chain"),
                    source_id=source.id,
                    target_id=target.id,
                    kind=EvidenceGraphEdgeKind.LEADS_TO,
                    confidence=confidence,
                    reason=(
                        f"{source.label} temporally precedes {target.label} "
                        f"in the incident evidence chain"
                    ),
                )
            )

    def _add_correlation_edges(self) -> None:
        entry_to_node = _entry_node_index(self._nodes)
        for correlation in self._timeline.correlations:
            source_node = entry_to_node.get(correlation.source.id)
            target_node = entry_to_node.get(correlation.target.id)
            if source_node is None or target_node is None:
                continue
            if _has_edge(self._edges, source_node.id, target_node.id):
                continue
            self._edges.append(
                EvidenceGraphEdge(
                    key=self._next_edge_key("correlation"),
                    source_id=source_node.id,
                    target_id=target_node.id,
                    kind=_graph_edge_kind(correlation.kind),
                    confidence=correlation.correlation_score,
                    reason=correlation.reason,
                )
            )

        if self._timeline.service_correlation is None:
            return

        for relationship in self._timeline.service_correlation.relationships:
            source_node = entry_to_node.get(relationship.source_entry_id or "")
            target_node = entry_to_node.get(relationship.target_entry_id or "")
            if source_node is None or target_node is None:
                continue
            if _has_edge(self._edges, source_node.id, target_node.id):
                continue
            self._edges.append(
                EvidenceGraphEdge(
                    key=self._next_edge_key("service"),
                    source_id=source_node.id,
                    target_id=target_node.id,
                    kind=EvidenceGraphEdgeKind.CORRELATES_WITH,
                    confidence=relationship.correlation_score,
                    reason=relationship.reason,
                )
            )

    def _resolve_service_name(self, error: TimelineEntry | None) -> str | None:
        if error is None:
            return None
        service_id = error.metadata.get("service_id")
        if service_id is None:
            return None
        return self._service_names.get(int(service_id))

    def _next_edge_key(self, prefix: str) -> str:
        self._edge_counter += 1
        return f"edge:{prefix}-{self._edge_counter}"


def _node_from_entry(
    *,
    node_id: str,
    kind: EvidenceGraphNodeKind,
    entry: TimelineEntry,
    label: str,
    confidence: float,
    description: str,
) -> EvidenceGraphNode:
    return EvidenceGraphNode(
        id=node_id,
        kind=kind,
        label=label,
        timestamp=entry.timestamp,
        event_reference=_entry_reference(entry),
        confidence=confidence,
        description=description,
    )


def _entry_reference(entry: TimelineEntry | None) -> EventReference:
    if entry is None:
        return EventReference()
    return EventReference(
        event_id=entry.event_id,
        error_group_id=entry.error_group_id,
        timeline_entry_id=entry.id,
    )


def _first_metric_anomaly(entries: Sequence[TimelineEntry]) -> TimelineEntry | None:
    for entry in entries:
        if is_metric_anomaly_entry(entry):
            return entry
    return None


def _is_metric_anomaly_candidate(entry: TimelineEntry) -> bool:
    if is_metric_anomaly_entry(entry):
        return True
    return entry.category is TimelineCategory.METRIC


def _chain_edge_confidence(
    *,
    source: EvidenceGraphNode,
    target: EvidenceGraphNode,
    correlations: Sequence,
) -> float:
    for correlation in correlations:
        source_match = correlation.source.timestamp == source.timestamp
        target_match = correlation.target.timestamp == target.timestamp
        if source_match and target_match:
            return round(correlation.correlation_score, 4)

    lag = target.timestamp - source.timestamp
    if lag.total_seconds() < 0:
        return 0.2

    hours = lag.total_seconds() / 3600
    return round(max(0.3, min(0.95, 0.95 - (hours * 0.1))), 4)


def _entry_node_index(
    nodes: dict[EvidenceGraphNodeKind, EvidenceGraphNode],
) -> dict[str, EvidenceGraphNode]:
    kind_priority = {kind: index for index, kind in enumerate(_CHAIN_ORDER)}
    mapping: dict[str, EvidenceGraphNode] = {}
    for kind in _CHAIN_ORDER:
        node = nodes.get(kind)
        if node is None:
            continue
        entry_id = node.event_reference.timeline_entry_id
        if not entry_id:
            continue
        existing = mapping.get(entry_id)
        if existing is None or kind_priority[kind] < kind_priority[existing.kind]:
            mapping[entry_id] = node
    return mapping


def _has_edge(
    edges: Sequence[EvidenceGraphEdge],
    source_id: str,
    target_id: str,
) -> bool:
    return any(
        edge.source_id == source_id and edge.target_id == target_id for edge in edges
    )


def _graph_edge_kind(kind: CorrelationKind) -> EvidenceGraphEdgeKind:
    if kind is CorrelationKind.DEPLOYMENT_TO_ERROR:
        return EvidenceGraphEdgeKind.ESCALATED_TO
    return EvidenceGraphEdgeKind.CORRELATES_WITH


def _build_graph_summary(chain: Sequence[str]) -> str:
    if not chain:
        return "No evidence chain could be constructed from timeline data"
    return "Evidence chain: " + " -> ".join(chain)
