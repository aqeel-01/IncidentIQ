"""Evidence package construction from timeline outputs."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.correlation.types import CorrelationKind
from app.domain.evidence.graph import build_evidence_graph
from app.domain.evidence.quality import score_evidence_quality
from app.domain.evidence.types import (
    EventReference,
    Evidence,
    EvidenceGraph,
    EvidenceGroup,
    EvidenceRelation,
    EvidenceRelationKind,
    EvidenceSource,
    EvidenceStance,
)
from app.domain.timeline.types import TimelineEntry, TimelineResult


def build_evidence_group(
    timeline: TimelineResult,
    *,
    built_at: datetime | None = None,
    engine_version: str = "1.0",
    service_names: dict[int, str] | None = None,
    affected_service: str | None = None,
) -> EvidenceGroup:
    """Aggregate timeline correlation outputs into a structured evidence package."""

    builder = _EvidenceGroupBuilder(
        incident_id=timeline.incident_id,
        project_id=timeline.project_id,
        built_at=built_at or datetime.now(UTC),
        engine_version=engine_version,
    )

    builder.add_timeline_markers(timeline.markers)
    builder.add_temporal_correlations(timeline.correlations)
    builder.add_deployment_correlation(timeline.deployment_correlation)
    builder.add_service_correlation(timeline.service_correlation)
    builder.add_metric_anomalies(timeline.entries)

    evidence_graph = build_evidence_graph(
        timeline,
        service_names=service_names,
        affected_service=affected_service,
    )

    package = builder.build(
        summary=_build_summary(timeline),
        evidence_graph=evidence_graph,
    )
    quality = score_evidence_quality(package)
    return package.model_copy(
        update={
            "quality": quality,
            "metadata": {
                **package.metadata,
                "quality_score": quality.score,
            },
        },
    )


class _EvidenceGroupBuilder:
    def __init__(
        self,
        *,
        incident_id: int,
        project_id: int,
        built_at: datetime,
        engine_version: str,
    ) -> None:
        self._incident_id = incident_id
        self._project_id = project_id
        self._built_at = built_at
        self._engine_version = engine_version
        self._evidence: list[Evidence] = []
        self._relations: list[EvidenceRelation] = []
        self._counter = 0

    def add_timeline_markers(self, markers) -> None:
        marker_map = {
            "first_anomaly": markers.first_anomaly,
            "first_relevant_error": markers.first_relevant_error,
            "first_alert": markers.first_alert,
            "recent_deployment": markers.recent_deployment,
            "recovery": markers.recovery,
        }
        for marker_name, entry in marker_map.items():
            if entry is None:
                continue
            self._add_entry_evidence(
                entry,
                source=EvidenceSource.TIMELINE_MARKER,
                description=f"Timeline marker identified: {marker_name}",
                confidence=0.7,
                stance=EvidenceStance.NEUTRAL,
                key_prefix=f"marker-{marker_name}",
            )

    def add_temporal_correlations(self, correlations) -> None:
        for index, correlation in enumerate(correlations):
            source_key = self._add_entry_evidence(
                correlation.source,
                source=EvidenceSource.TEMPORAL_CORRELATION,
                description=correlation.reason,
                confidence=correlation.correlation_score,
                stance=EvidenceStance.SUPPORTING,
                key_prefix=f"temporal-source-{index}",
            )
            target_key = self._add_entry_evidence(
                correlation.target,
                source=EvidenceSource.TEMPORAL_CORRELATION,
                description=correlation.reason,
                confidence=correlation.correlation_score,
                stance=EvidenceStance.SUPPORTING,
                key_prefix=f"temporal-target-{index}",
            )
            self._relations.append(
                EvidenceRelation(
                    key=f"rel-temporal-{index}",
                    source_evidence_key=source_key,
                    target_evidence_key=target_key,
                    kind=_temporal_relation_kind(correlation.kind),
                    confidence=correlation.correlation_score,
                    description=correlation.reason,
                )
            )

    def add_deployment_correlation(self, assessment) -> None:
        if assessment is None:
            return

        supporting_keys: list[str] = []
        contradicting_keys: list[str] = []

        for item in assessment.supporting_evidence:
            key = self._next_key("deployment-support")
            self._evidence.append(
                Evidence(
                    key=key,
                    source=EvidenceSource.DEPLOYMENT_CORRELATION,
                    timestamp=assessment.deployment.timestamp
                    if assessment.deployment is not None
                    else self._built_at,
                    event_reference=_entry_reference(assessment.deployment),
                    description=item.detail,
                    value=item.kind.value,
                    confidence=min(1.0, item.weight),
                    supporting_or_contradicting=EvidenceStance.SUPPORTING,
                )
            )
            supporting_keys.append(key)

        for item in assessment.contradicting_evidence:
            key = self._next_key("deployment-contradict")
            self._evidence.append(
                Evidence(
                    key=key,
                    source=EvidenceSource.DEPLOYMENT_CORRELATION,
                    timestamp=assessment.deployment.timestamp
                    if assessment.deployment is not None
                    else self._built_at,
                    event_reference=_entry_reference(assessment.deployment),
                    description=item.detail,
                    value=item.kind.value,
                    confidence=min(1.0, item.weight),
                    supporting_or_contradicting=EvidenceStance.CONTRADICTING,
                )
            )
            contradicting_keys.append(key)

        for support_key in supporting_keys:
            for contradict_key in contradicting_keys:
                self._relations.append(
                    EvidenceRelation(
                        key=self._next_key("deployment-rel"),
                        source_evidence_key=support_key,
                        target_evidence_key=contradict_key,
                        kind=EvidenceRelationKind.CONTRADICTS,
                        confidence=0.5,
                        description="Deployment supporting and contradicting signals",
                    )
                )

    def add_service_correlation(self, result) -> None:
        if result is None:
            return

        for index, relationship in enumerate(result.relationships):
            source_key = self._next_key("service-source")
            self._evidence.append(
                Evidence(
                    key=source_key,
                    source=EvidenceSource.SERVICE_CORRELATION,
                    timestamp=self._built_at,
                    event_reference=EventReference(
                        timeline_entry_id=relationship.source_entry_id,
                    ),
                    description=relationship.reason,
                    value=relationship.kind.value,
                    confidence=relationship.correlation_score,
                    supporting_or_contradicting=EvidenceStance.SUPPORTING,
                )
            )
            target_key = self._next_key("service-target")
            self._evidence.append(
                Evidence(
                    key=target_key,
                    source=EvidenceSource.SERVICE_CORRELATION,
                    timestamp=self._built_at,
                    event_reference=EventReference(
                        timeline_entry_id=relationship.target_entry_id,
                    ),
                    description=relationship.target_label,
                    value=relationship.kind.value,
                    confidence=relationship.correlation_score,
                    supporting_or_contradicting=EvidenceStance.SUPPORTING,
                )
            )
            for signal in relationship.evidence:
                self._evidence.append(
                    Evidence(
                        key=self._next_key("service-signal"),
                        source=EvidenceSource.SERVICE_CORRELATION,
                        timestamp=self._built_at,
                        event_reference=EventReference(
                            timeline_entry_id=relationship.source_entry_id,
                        ),
                        description=signal.detail,
                        value=signal.signal.value,
                        confidence=min(1.0, signal.weight),
                        supporting_or_contradicting=EvidenceStance.SUPPORTING,
                    )
                )
            self._relations.append(
                EvidenceRelation(
                    key=f"rel-service-{index}",
                    source_evidence_key=source_key,
                    target_evidence_key=target_key,
                    kind=EvidenceRelationKind.CORRELATES_WITH,
                    confidence=relationship.correlation_score,
                    description=relationship.reason,
                )
            )

    def add_metric_anomalies(self, entries) -> None:
        for index, entry in enumerate(entries):
            if not entry.metadata.get("anomaly"):
                continue
            normalized = entry.metadata.get("normalized_data", {})
            self._add_entry_evidence(
                entry,
                source=EvidenceSource.ANOMALY_DETECTION,
                description=(
                    f"Metric anomaly detected for "
                    f"{normalized.get('metric_name', entry.title)}"
                ),
                confidence=0.8,
                stance=EvidenceStance.SUPPORTING,
                value=normalized.get("value"),
                key_prefix=f"anomaly-{index}",
            )

    def build(
        self,
        *,
        summary: str | None,
        evidence_graph: EvidenceGraph | None = None,
    ) -> EvidenceGroup:
        return EvidenceGroup(
            incident_id=self._incident_id,
            project_id=self._project_id,
            built_at=self._built_at,
            engine_version=self._engine_version,
            summary=summary,
            evidence=self._evidence,
            relations=self._relations,
            evidence_graph=evidence_graph,
            metadata={
                "evidence_count": len(self._evidence),
                "relation_count": len(self._relations),
                "graph_node_count": len(evidence_graph.nodes) if evidence_graph else 0,
                "graph_edge_count": len(evidence_graph.edges) if evidence_graph else 0,
            },
        )

    def _add_entry_evidence(
        self,
        entry: TimelineEntry,
        *,
        source: EvidenceSource,
        description: str,
        confidence: float,
        stance: EvidenceStance,
        key_prefix: str,
        value: str | float | int | bool | None = None,
    ) -> str:
        key = self._next_key(key_prefix)
        self._evidence.append(
            Evidence(
                key=key,
                source=source,
                timestamp=entry.timestamp,
                event_reference=_entry_reference(entry),
                description=description,
                value=value,
                confidence=confidence,
                supporting_or_contradicting=stance,
            )
        )
        return key

    def _next_key(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"


def _entry_reference(entry: TimelineEntry | None) -> EventReference:
    if entry is None:
        return EventReference()
    return EventReference(
        event_id=entry.event_id,
        error_group_id=entry.error_group_id,
        timeline_entry_id=entry.id,
    )


def _temporal_relation_kind(kind: CorrelationKind) -> EvidenceRelationKind:
    if kind is CorrelationKind.DEPLOYMENT_TO_ERROR:
        return EvidenceRelationKind.CAUSED_BY
    return EvidenceRelationKind.CORRELATES_WITH


def _build_summary(timeline: TimelineResult) -> str:
    parts = [
        f"{len(timeline.entries)} timeline entries",
        f"{len(timeline.correlations)} temporal correlations",
    ]
    if timeline.deployment_correlation is not None:
        parts.append(
            "deployment related"
            if timeline.deployment_correlation.is_related
            else "deployment not related"
        )
    if timeline.service_correlation is not None:
        parts.append(
            f"{len(timeline.service_correlation.relationships)} service relationships"
        )
    return "; ".join(parts)
