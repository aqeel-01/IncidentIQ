"""Extract grounded evidence identifiers from an RCA evidence package."""

from __future__ import annotations

from app.domain.rca.package import RCAEvidencePackage


def extract_package_evidence_keys(package: RCAEvidencePackage) -> list[str]:
    """Collect identifiers/labels that citations may legitimately reference."""

    keys: list[str] = []

    def _add(value: str | None) -> None:
        if value and value not in keys:
            keys.append(value)

    incident = package.incident
    _add(f"incident:{incident.incident_id}")
    _add(incident.title)
    _add(incident.service)

    for symptom in package.symptoms:
        _add(symptom.id)
        _add(symptom.title)
        _add(symptom.service)

    for group in package.error_groups:
        _add(group.id)
        _add(group.title)
        _add(group.service)

    for anomaly in package.anomalies:
        _add(anomaly.id)
        _add(anomaly.title)
        _add(anomaly.metric_name)

    for deployment in package.deployments:
        _add(deployment.id)
        _add(deployment.title)
        _add(deployment.version)
        _add(deployment.service)

    for item in package.timeline:
        _add(item.id)
        _add(item.title)

    for correlation in package.correlations:
        _add(correlation.kind)
        _add(correlation.source)
        _add(correlation.target)
        _add(correlation.reason)

    if package.evidence_graph is not None:
        for node in package.evidence_graph.nodes:
            _add(node.id)
            _add(node.label)
            _add(node.kind)
        for edge in package.evidence_graph.edges:
            _add(edge.source_id)
            _add(edge.target_id)
            _add(edge.kind)
            _add(edge.reason)
        for node_id in package.evidence_graph.chain:
            _add(node_id)

    return keys
