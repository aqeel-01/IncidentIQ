"""Synthetic RCA benchmark incidents with known root causes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.rca.eval.types import BenchmarkCase, BenchmarkDataset, GoldLabel
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
    RCAIncidentContext,
    RCASymptom,
    RCATimelineItem,
)
from app.domain.rca.types import RCAStatus

_BASE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _ts(minutes: int) -> datetime:
    return _BASE + timedelta(minutes=minutes)


def _quality(score: int = 82) -> RCAEvidenceQualitySummary:
    return RCAEvidenceQualitySummary(
        score=score,
        summary="Synthetic evidence package for RCA evaluation.",
        source_diversity=80.0,
        temporal_consistency=85.0,
        correlation_strength=78.0,
        completeness=75.0,
        consistency=80.0,
    )


def _incident(
    *,
    incident_id: int,
    title: str,
    service: str,
    severity: str = "high",
) -> RCAIncidentContext:
    return RCAIncidentContext(
        incident_id=incident_id,
        project_id=1,
        title=title,
        environment="production",
        severity=severity,
        status="investigating",
        service=service,
        started_at=_ts(0),
        ended_at=None,
        occurrence_count=1,
    )


def case_deployment_regression() -> BenchmarkCase:
    package = RCAEvidencePackage(
        incident=_incident(
            incident_id=101,
            title="Payments API elevated errors after release",
            service="payments-api",
        ),
        symptoms=[
            RCASymptom(
                id="symptom:alert-high-error",
                kind="alert",
                timestamp=_ts(20),
                title="HighErrorRate",
                severity="critical",
                service="payments-api",
            ),
            RCASymptom(
                id="symptom:log-timeout",
                kind="log",
                timestamp=_ts(22),
                title="database timeout",
                severity="error",
                service="payments-api",
            ),
        ],
        error_groups=[
            RCAErrorGroupSummary(
                id="error_group:db-timeout",
                title="database timeout",
                first_seen=_ts(18),
                occurrence_count=42,
                severity="error",
                service="payments-api",
            )
        ],
        anomalies=[
            RCAAnomalySummary(
                id="anomaly:error-rate",
                timestamp=_ts(15),
                metric_name="error_rate",
                value=0.91,
                title="error_rate spike",
            )
        ],
        deployments=[
            RCADeploymentSummary(
                id="deploy:payments-v122",
                timestamp=_ts(0),
                title="payments-api v1.2.2",
                version="v1.2.2",
                service="payments-api",
            )
        ],
        timeline=[
            RCATimelineItem(
                id="timeline:deploy",
                category="deployment",
                timestamp=_ts(0),
                title="Deployed payments-api v1.2.2",
            ),
            RCATimelineItem(
                id="timeline:anomaly",
                category="anomaly",
                timestamp=_ts(15),
                title="error_rate spike",
                severity="high",
            ),
            RCATimelineItem(
                id="timeline:errors",
                category="error",
                timestamp=_ts(18),
                title="database timeout",
                severity="error",
            ),
        ],
        correlations=[
            RCACorrelationSummary(
                kind="deployment_to_error",
                source="v1.2.2",
                target="database timeout",
                score=0.88,
                time_difference_seconds=1080,
                reason="Deployment preceded error spike",
            )
        ],
        evidence_graph=RCAEvidenceGraphSummary(
            chain=["node:deploy", "node:anomaly", "node:error", "node:incident"],
            nodes=[
                RCAEvidenceGraphNodeSummary(
                    id="node:deploy",
                    kind="deployment",
                    label="payments-api v1.2.2",
                    timestamp=_ts(0),
                    confidence=0.9,
                ),
                RCAEvidenceGraphNodeSummary(
                    id="node:anomaly",
                    kind="anomaly",
                    label="error_rate spike",
                    timestamp=_ts(15),
                    confidence=0.85,
                ),
                RCAEvidenceGraphNodeSummary(
                    id="node:error",
                    kind="error",
                    label="database timeout",
                    timestamp=_ts(18),
                    confidence=0.9,
                ),
                RCAEvidenceGraphNodeSummary(
                    id="node:incident",
                    kind="incident",
                    label="Payments API elevated errors after release",
                    timestamp=_ts(20),
                    confidence=0.95,
                ),
            ],
            edges=[
                RCAEvidenceGraphEdgeSummary(
                    source_id="node:deploy",
                    target_id="node:anomaly",
                    kind="preceded",
                    confidence=0.85,
                    reason="Deploy then metric spike",
                )
            ],
            summary="Release precedes metric and error escalation.",
        ),
        evidence_quality=_quality(86),
    )
    return BenchmarkCase(
        id="deploy-regression-payments",
        description="Clear deployment regression on payments-api.",
        package=package,
        gold=GoldLabel(
            root_cause_title="Deployment regression",
            root_cause_aliases=[
                "bad deployment",
                "faulty release",
                "payments-api v1.2.2 regression",
                "deploy caused outage",
            ],
            expected_status=RCAStatus.CONFIDENT,
            ranked_hypothesis_titles=[
                "Deployment regression",
                "Database saturation",
                "Upstream dependency failure",
            ],
            supporting_evidence_keys=[
                "deploy:payments-v122",
                "error_group:db-timeout",
                "anomaly:error-rate",
                "deployment_to_error",
            ],
            valid_evidence_keys=["v1.2.2", "database timeout", "error_rate spike"],
        ),
    )


def case_upstream_dependency() -> BenchmarkCase:
    package = RCAEvidencePackage(
        incident=_incident(
            incident_id=102,
            title="Checkout failures while auth is degraded",
            service="checkout-api",
        ),
        symptoms=[
            RCASymptom(
                id="symptom:auth-5xx",
                kind="alert",
                timestamp=_ts(5),
                title="AuthService5xx",
                severity="critical",
                service="auth-service",
            ),
            RCASymptom(
                id="symptom:checkout-timeout",
                kind="log",
                timestamp=_ts(8),
                title="auth token request timeout",
                severity="error",
                service="checkout-api",
            ),
        ],
        error_groups=[
            RCAErrorGroupSummary(
                id="error_group:auth-timeout",
                title="auth token request timeout",
                first_seen=_ts(6),
                occurrence_count=30,
                service="checkout-api",
            )
        ],
        anomalies=[
            RCAAnomalySummary(
                id="anomaly:auth-latency",
                timestamp=_ts(3),
                metric_name="auth_p99_latency_ms",
                value=4200,
                title="auth latency spike",
            )
        ],
        deployments=[],
        timeline=[
            RCATimelineItem(
                id="timeline:auth-latency",
                category="anomaly",
                timestamp=_ts(3),
                title="auth latency spike",
                severity="high",
            ),
            RCATimelineItem(
                id="timeline:auth-alert",
                category="alert",
                timestamp=_ts(5),
                title="AuthService5xx",
                severity="critical",
            ),
            RCATimelineItem(
                id="timeline:checkout-errors",
                category="error",
                timestamp=_ts(8),
                title="auth token request timeout",
                severity="error",
            ),
        ],
        correlations=[
            RCACorrelationSummary(
                kind="upstream_to_downstream",
                source="auth-service",
                target="checkout-api",
                score=0.9,
                time_difference_seconds=180,
                reason="Auth degradation preceded checkout timeouts",
            )
        ],
        evidence_graph=RCAEvidenceGraphSummary(
            chain=["node:auth", "node:checkout", "node:incident"],
            nodes=[
                RCAEvidenceGraphNodeSummary(
                    id="node:auth",
                    kind="service",
                    label="auth-service",
                    timestamp=_ts(3),
                    confidence=0.9,
                ),
                RCAEvidenceGraphNodeSummary(
                    id="node:checkout",
                    kind="service",
                    label="checkout-api",
                    timestamp=_ts(8),
                    confidence=0.85,
                ),
                RCAEvidenceGraphNodeSummary(
                    id="node:incident",
                    kind="incident",
                    label="Checkout failures while auth is degraded",
                    timestamp=_ts(8),
                    confidence=0.9,
                ),
            ],
            edges=[
                RCAEvidenceGraphEdgeSummary(
                    source_id="node:auth",
                    target_id="node:checkout",
                    kind="dependency_failure",
                    confidence=0.9,
                    reason="Checkout depends on auth tokens",
                )
            ],
            summary="Upstream auth failure cascades to checkout.",
        ),
        evidence_quality=_quality(84),
    )
    return BenchmarkCase(
        id="upstream-auth-dependency",
        description="Checkout outage caused by upstream auth-service failure.",
        package=package,
        gold=GoldLabel(
            root_cause_title="Upstream dependency failure",
            root_cause_aliases=[
                "auth-service failure",
                "upstream auth outage",
                "dependency failure",
            ],
            expected_status=RCAStatus.CONFIDENT,
            ranked_hypothesis_titles=[
                "Upstream dependency failure",
                "Checkout application bug",
                "Network partition",
            ],
            supporting_evidence_keys=[
                "symptom:auth-5xx",
                "anomaly:auth-latency",
                "error_group:auth-timeout",
                "upstream_to_downstream",
            ],
        ),
    )


def case_config_misconfiguration() -> BenchmarkCase:
    package = RCAEvidencePackage(
        incident=_incident(
            incident_id=103,
            title="Search API returning empty results after config change",
            service="search-api",
            severity="medium",
        ),
        symptoms=[
            RCASymptom(
                id="symptom:empty-results",
                kind="alert",
                timestamp=_ts(12),
                title="EmptySearchResults",
                severity="warning",
                service="search-api",
            )
        ],
        error_groups=[
            RCAErrorGroupSummary(
                id="error_group:index-missing",
                title="index alias not found",
                first_seen=_ts(10),
                occurrence_count=18,
                service="search-api",
            )
        ],
        anomalies=[],
        deployments=[
            RCADeploymentSummary(
                id="deploy:config-rollout",
                timestamp=_ts(0),
                title="search-api config rollout",
                version="config-2026-09-01",
                service="search-api",
            )
        ],
        timeline=[
            RCATimelineItem(
                id="timeline:config",
                category="deployment",
                timestamp=_ts(0),
                title="search-api config rollout",
            ),
            RCATimelineItem(
                id="timeline:index-error",
                category="error",
                timestamp=_ts(10),
                title="index alias not found",
                severity="error",
            ),
        ],
        correlations=[
            RCACorrelationSummary(
                kind="config_to_error",
                source="config-2026-09-01",
                target="index alias not found",
                score=0.86,
                time_difference_seconds=600,
                reason="Config change pointed search-api at missing index alias",
            )
        ],
        evidence_graph=None,
        evidence_quality=_quality(78),
    )
    return BenchmarkCase(
        id="config-misconfiguration-search",
        description="Bad config rollout breaks search index alias.",
        package=package,
        gold=GoldLabel(
            root_cause_title="Configuration error",
            root_cause_aliases=[
                "misconfiguration",
                "bad config rollout",
                "incorrect index alias",
            ],
            expected_status=RCAStatus.CONFIDENT,
            ranked_hypothesis_titles=[
                "Configuration error",
                "OpenSearch cluster outage",
                "Client caching bug",
            ],
            supporting_evidence_keys=[
                "deploy:config-rollout",
                "error_group:index-missing",
                "config_to_error",
            ],
        ),
    )


def case_resource_exhaustion() -> BenchmarkCase:
    package = RCAEvidencePackage(
        incident=_incident(
            incident_id=104,
            title="Worker pods crash looping under load",
            service="ingest-worker",
        ),
        symptoms=[
            RCASymptom(
                id="symptom:oom",
                kind="alert",
                timestamp=_ts(25),
                title="PodOOMKilled",
                severity="critical",
                service="ingest-worker",
            )
        ],
        error_groups=[
            RCAErrorGroupSummary(
                id="error_group:oom",
                title="java.lang.OutOfMemoryError",
                first_seen=_ts(20),
                occurrence_count=14,
                service="ingest-worker",
            )
        ],
        anomalies=[
            RCAAnomalySummary(
                id="anomaly:memory",
                timestamp=_ts(15),
                metric_name="container_memory_working_set_bytes",
                value=3_900_000_000,
                title="memory near limit",
            ),
            RCAAnomalySummary(
                id="anomaly:queue-depth",
                timestamp=_ts(10),
                metric_name="ingest_queue_depth",
                value=50000,
                title="ingest queue depth surge",
            ),
        ],
        deployments=[],
        timeline=[
            RCATimelineItem(
                id="timeline:queue",
                category="anomaly",
                timestamp=_ts(10),
                title="ingest queue depth surge",
                severity="high",
            ),
            RCATimelineItem(
                id="timeline:memory",
                category="anomaly",
                timestamp=_ts(15),
                title="memory near limit",
                severity="high",
            ),
            RCATimelineItem(
                id="timeline:oom",
                category="alert",
                timestamp=_ts(25),
                title="PodOOMKilled",
                severity="critical",
            ),
        ],
        correlations=[
            RCACorrelationSummary(
                kind="queue_to_oom",
                source="ingest_queue_depth",
                target="PodOOMKilled",
                score=0.83,
                time_difference_seconds=900,
                reason="Queue surge preceded memory exhaustion",
            )
        ],
        evidence_graph=None,
        evidence_quality=_quality(80),
    )
    return BenchmarkCase(
        id="resource-exhaustion-oom",
        description="Ingest workers OOM after queue backlog.",
        package=package,
        gold=GoldLabel(
            root_cause_title="Resource exhaustion",
            root_cause_aliases=[
                "out of memory",
                "memory exhaustion",
                "OOM kill",
                "capacity exhaustion",
            ],
            expected_status=RCAStatus.CONFIDENT,
            ranked_hypothesis_titles=[
                "Resource exhaustion",
                "Memory leak in worker",
                "Bad deployment",
            ],
            supporting_evidence_keys=[
                "symptom:oom",
                "anomaly:memory",
                "anomaly:queue-depth",
                "error_group:oom",
            ],
        ),
    )


def case_db_pool_exhaustion() -> BenchmarkCase:
    package = RCAEvidencePackage(
        incident=_incident(
            incident_id=105,
            title="API latency cliff with connection wait timeouts",
            service="orders-api",
        ),
        symptoms=[
            RCASymptom(
                id="symptom:pool-wait",
                kind="log",
                timestamp=_ts(14),
                title="HikariPool connection acquisition timeout",
                severity="error",
                service="orders-api",
            )
        ],
        error_groups=[
            RCAErrorGroupSummary(
                id="error_group:pool-timeout",
                title="HikariPool connection acquisition timeout",
                first_seen=_ts(12),
                occurrence_count=55,
                service="orders-api",
            )
        ],
        anomalies=[
            RCAAnomalySummary(
                id="anomaly:pool-usage",
                timestamp=_ts(8),
                metric_name="db_pool_active_connections",
                value=100,
                title="db pool saturated",
            ),
            RCAAnomalySummary(
                id="anomaly:latency",
                timestamp=_ts(10),
                metric_name="http_request_duration_p99",
                value=8.5,
                title="p99 latency spike",
            ),
        ],
        deployments=[
            RCADeploymentSummary(
                id="deploy:orders-feature",
                timestamp=_ts(-120),
                title="orders-api feature flag batch queries",
                version="v3.4.1",
                service="orders-api",
            )
        ],
        timeline=[
            RCATimelineItem(
                id="timeline:pool",
                category="anomaly",
                timestamp=_ts(8),
                title="db pool saturated",
                severity="high",
            ),
            RCATimelineItem(
                id="timeline:timeouts",
                category="error",
                timestamp=_ts(12),
                title="HikariPool connection acquisition timeout",
                severity="error",
            ),
        ],
        correlations=[
            RCACorrelationSummary(
                kind="pool_to_latency",
                source="db_pool_active_connections",
                target="http_request_duration_p99",
                score=0.87,
                time_difference_seconds=120,
                reason="Pool saturation aligns with latency cliff",
            )
        ],
        evidence_graph=None,
        evidence_quality=_quality(81),
    )
    return BenchmarkCase(
        id="db-pool-exhaustion-orders",
        description="Orders API stalls because the DB connection pool is exhausted.",
        package=package,
        gold=GoldLabel(
            root_cause_title="Database connection pool exhaustion",
            root_cause_aliases=[
                "connection pool exhaustion",
                "HikariPool exhaustion",
                "DB pool saturated",
            ],
            expected_status=RCAStatus.CONFIDENT,
            ranked_hypothesis_titles=[
                "Database connection pool exhaustion",
                "Database host failure",
                "Deployment regression",
            ],
            supporting_evidence_keys=[
                "anomaly:pool-usage",
                "error_group:pool-timeout",
                "symptom:pool-wait",
                "pool_to_latency",
            ],
        ),
    )


def case_insufficient_evidence() -> BenchmarkCase:
    package = RCAEvidencePackage(
        incident=_incident(
            incident_id=106,
            title="Brief blip with sparse telemetry",
            service="unknown-service",
            severity="low",
        ),
        symptoms=[
            RCASymptom(
                id="symptom:brief-alert",
                kind="alert",
                timestamp=_ts(0),
                title="TransientLatency",
                severity="warning",
                service="unknown-service",
            )
        ],
        error_groups=[],
        anomalies=[],
        deployments=[],
        timeline=[
            RCATimelineItem(
                id="timeline:blip",
                category="alert",
                timestamp=_ts(0),
                title="TransientLatency",
                severity="warning",
            )
        ],
        correlations=[],
        evidence_graph=None,
        evidence_quality=_quality(22),
    )
    return BenchmarkCase(
        id="insufficient-evidence-blip",
        description=(
            "Sparse telemetry; model should avoid a confident wrong root cause."
        ),
        package=package,
        gold=GoldLabel(
            root_cause_title="Insufficient evidence",
            root_cause_aliases=["unknown", "inconclusive"],
            expected_status=RCAStatus.NO_CONFIDENT_ROOT_CAUSE,
            allow_no_root_cause=True,
            ranked_hypothesis_titles=[],
            supporting_evidence_keys=["symptom:brief-alert"],
        ),
    )


def build_synthetic_benchmark() -> BenchmarkDataset:
    """Return the built-in synthetic RCA benchmark dataset."""

    return BenchmarkDataset(
        name="incidentiq-rca-benchmark",
        version="1.0",
        cases=[
            case_deployment_regression(),
            case_upstream_dependency(),
            case_config_misconfiguration(),
            case_resource_exhaustion(),
            case_db_pool_exhaustion(),
            case_insufficient_evidence(),
        ],
    )
