"""Build the structured RCA evidence package from investigation data."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db.models.incident import Incident
from app.domain.correlation import is_metric_anomaly_entry
from app.domain.evidence.types import EvidenceGraph
from app.domain.rca.package import (
    RCAAnomalySummary,
    RCACorrelationSummary,
    RCADeploymentSummary,
    RCAErrorGroupSummary,
    RCAEvidenceGraphEdgeSummary,
    RCAEvidenceGraphNodeSummary,
    RCAEvidenceGraphSummary,
    RCAEvidencePackage,
    RCAEvidenceQualitySummary,
    RCAHistoricalContext,
    RCAIncidentContext,
    RCASymptom,
    RCATimelineItem,
)
from app.domain.timeline.types import TimelineCategory, TimelineEntry, TimelineResult


def build_rca_evidence_package(
    *,
    incident: Incident | RCAIncidentContext,
    timeline: TimelineResult,
    service_names: dict[int, str] | None = None,
    historical_context: RCAHistoricalContext | None = None,
) -> RCAEvidencePackage:
    """Build the deterministic RCA evidence package for AI consumption."""

    builder = _RCAEvidencePackageBuilder(
        incident=_incident_context(incident),
        timeline=timeline,
        service_names=service_names or {},
        historical_context=historical_context,
    )
    return builder.build()


def package_to_canonical_json(package: RCAEvidencePackage) -> str:
    """Serialize a package to canonical JSON for snapshot comparisons."""

    return json.dumps(
        package.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    )


class _RCAEvidencePackageBuilder:
    def __init__(
        self,
        *,
        incident: RCAIncidentContext,
        timeline: TimelineResult,
        service_names: dict[int, str],
        historical_context: RCAHistoricalContext | None,
    ) -> None:
        self._incident = incident
        self._timeline = timeline
        self._service_names = service_names
        self._historical_context = historical_context

    def build(self) -> RCAEvidencePackage:
        return RCAEvidencePackage(
            incident=self._incident,
            symptoms=self._build_symptoms(),
            error_groups=self._build_error_groups(),
            anomalies=self._build_anomalies(),
            deployments=self._build_deployments(),
            timeline=self._build_timeline(),
            correlations=self._build_correlations(),
            evidence_graph=self._build_evidence_graph(),
            evidence_quality=self._build_evidence_quality(),
            historical_context=self._historical_context,
        )

    def _build_symptoms(self) -> list[RCASymptom]:
        symptoms = [
            RCASymptom(
                id=entry.id,
                kind=entry.category.value,
                timestamp=_to_utc(entry.timestamp),
                title=entry.title,
                severity=_severity_value(entry),
                service=self._service_name(entry),
            )
            for entry in self._timeline.entries
            if entry.category in {TimelineCategory.ALERT, TimelineCategory.LOG}
        ]
        return _sort_by_timestamp(symptoms)

    def _build_error_groups(self) -> list[RCAErrorGroupSummary]:
        groups = [
            RCAErrorGroupSummary(
                id=entry.id,
                error_group_id=entry.error_group_id,
                title=entry.title,
                first_seen=_to_utc(entry.timestamp),
                occurrence_count=_occurrence_count(entry),
                severity=_severity_value(entry),
                service=self._service_name(entry),
            )
            for entry in self._timeline.entries
            if entry.category is TimelineCategory.ERROR
        ]
        return _sort_by_timestamp(groups)

    def _build_anomalies(self) -> list[RCAAnomalySummary]:
        anomalies = [
            RCAAnomalySummary(
                id=entry.id,
                timestamp=_to_utc(entry.timestamp),
                metric_name=_metric_name(entry),
                value=_metric_value(entry),
                title=entry.title,
            )
            for entry in self._timeline.entries
            if is_metric_anomaly_entry(entry)
        ]
        return _sort_by_timestamp(anomalies)

    def _build_deployments(self) -> list[RCADeploymentSummary]:
        deployments = [
            RCADeploymentSummary(
                id=entry.id,
                timestamp=_to_utc(entry.timestamp),
                title=entry.title,
                version=_deployment_version(entry),
                service=self._service_name(entry),
            )
            for entry in self._timeline.entries
            if entry.category is TimelineCategory.DEPLOYMENT
        ]
        return _sort_by_timestamp(deployments)

    def _build_timeline(self) -> list[RCATimelineItem]:
        items = [
            RCATimelineItem(
                id=entry.id,
                category=entry.category.value,
                timestamp=_to_utc(entry.timestamp),
                title=entry.title,
                severity=_severity_value(entry),
            )
            for entry in self._timeline.entries
        ]
        return _sort_by_timestamp(items)

    def _build_correlations(self) -> list[RCACorrelationSummary]:
        correlations: list[RCACorrelationSummary] = []

        for correlation in self._timeline.correlations:
            correlations.append(
                RCACorrelationSummary(
                    kind=correlation.kind.value,
                    source=correlation.source.title,
                    target=correlation.target.title,
                    score=round(correlation.correlation_score, 4),
                    time_difference_seconds=int(
                        correlation.time_difference.total_seconds()
                    ),
                    reason=correlation.reason,
                )
            )

        assessment = self._timeline.deployment_correlation
        if assessment is not None:
            correlations.append(
                RCACorrelationSummary(
                    kind="deployment_correlation",
                    source=assessment.deployment.title
                    if assessment.deployment is not None
                    else "deployment",
                    target="incident",
                    score=round(assessment.relationship_score, 4),
                    reason=assessment.summary,
                )
            )

        service_result = self._timeline.service_correlation
        if service_result is not None:
            for relationship in service_result.relationships:
                correlations.append(
                    RCACorrelationSummary(
                        kind=relationship.kind.value,
                        source=relationship.source_label,
                        target=relationship.target_label,
                        score=round(relationship.correlation_score, 4),
                        reason=relationship.reason,
                    )
                )

        return sorted(
            correlations,
            key=lambda item: (item.kind, item.source, item.target),
        )

    def _build_evidence_graph(self) -> RCAEvidenceGraphSummary | None:
        evidence_group = self._timeline.evidence_group
        if evidence_group is None or evidence_group.evidence_graph is None:
            return None
        return _graph_summary(evidence_group.evidence_graph)

    def _build_evidence_quality(self) -> RCAEvidenceQualitySummary | None:
        evidence_group = self._timeline.evidence_group
        if evidence_group is None or evidence_group.quality is None:
            return None
        quality = evidence_group.quality
        return RCAEvidenceQualitySummary(
            score=quality.score,
            summary=quality.summary,
            source_diversity=quality.breakdown.source_diversity,
            temporal_consistency=quality.breakdown.temporal_consistency,
            correlation_strength=quality.breakdown.correlation_strength,
            completeness=quality.breakdown.completeness,
            consistency=quality.breakdown.consistency,
        )

    def _service_name(self, entry: TimelineEntry) -> str | None:
        return _service_name(entry, self._service_names)


def _incident_context(incident: Incident | RCAIncidentContext) -> RCAIncidentContext:
    if isinstance(incident, RCAIncidentContext):
        return incident

    service_name = incident.service.name if incident.service is not None else None
    return RCAIncidentContext(
        incident_id=incident.id,
        project_id=incident.project_id,
        title=incident.title,
        environment=incident.environment,
        severity=incident.severity.value,
        status=incident.status.value,
        service=service_name,
        started_at=_to_utc(incident.started_at),
        ended_at=_to_utc(incident.ended_at) if incident.ended_at is not None else None,
        occurrence_count=incident.occurrence_count,
    )


def _graph_summary(graph: EvidenceGraph) -> RCAEvidenceGraphSummary:
    nodes = sorted(
        [
            RCAEvidenceGraphNodeSummary(
                id=node.id,
                kind=node.kind.value,
                label=node.label,
                timestamp=_to_utc(node.timestamp),
                confidence=node.confidence,
            )
            for node in graph.nodes
        ],
        key=lambda item: item.id,
    )
    edges = sorted(
        [
            RCAEvidenceGraphEdgeSummary(
                source_id=edge.source_id,
                target_id=edge.target_id,
                kind=edge.kind.value,
                confidence=edge.confidence,
                reason=edge.reason,
            )
            for edge in graph.edges
        ],
        key=lambda item: (item.source_id, item.target_id, item.kind),
    )
    return RCAEvidenceGraphSummary(
        chain=list(graph.chain),
        nodes=nodes,
        edges=edges,
        summary=graph.summary,
    )


def _service_name(
    entry: TimelineEntry,
    service_names: dict[int, str],
) -> str | None:
    service_id = entry.metadata.get("service_id")
    if service_id is None:
        return None
    return service_names.get(int(service_id))


def _severity_value(entry: TimelineEntry) -> str | None:
    if entry.severity is None:
        return None
    return entry.severity.value


def _occurrence_count(entry: TimelineEntry) -> int | None:
    value = entry.metadata.get("occurrence_count")
    if value is None:
        return None
    return int(value)


def _metric_name(entry: TimelineEntry) -> str:
    normalized = entry.metadata.get("normalized_data", {})
    if isinstance(normalized, dict):
        metric_name = normalized.get("metric_name")
        if isinstance(metric_name, str) and metric_name:
            return metric_name
    return entry.title


def _metric_value(entry: TimelineEntry) -> float | int | str | None:
    normalized = entry.metadata.get("normalized_data", {})
    if not isinstance(normalized, dict):
        return None
    value = normalized.get("value")
    if isinstance(value, (float, int, str)):
        return value
    return None


def _deployment_version(entry: TimelineEntry) -> str | None:
    normalized = entry.metadata.get("normalized_data", {})
    if not isinstance(normalized, dict):
        return entry.title
    version = normalized.get("version")
    if isinstance(version, str) and version:
        return version
    return entry.title


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _sort_by_timestamp(items: list) -> list:
    return sorted(items, key=_timestamp_sort_key)


def _timestamp_sort_key(item) -> tuple:
    timestamp = getattr(item, "timestamp", None)
    if timestamp is None:
        timestamp = item.first_seen
    return (timestamp, item.id)
