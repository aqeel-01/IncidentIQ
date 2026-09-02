"""Temporal correlation between incident events."""

from app.domain.correlation.config import (
    correlation_thresholds_from_settings,
    deployment_correlation_thresholds_from_settings,
    service_correlation_thresholds_from_settings,
)
from app.domain.correlation.deployment import evaluate_deployment_correlation
from app.domain.correlation.engine import (
    annotate_metric_anomalies,
    correlate_temporal,
    correlation_score,
    is_error_entry,
    is_metric_anomaly_entry,
)
from app.domain.correlation.service_correlation import (
    correlate_service_metric_error,
    infer_dependencies_from_traces,
)
from app.domain.correlation.types import (
    CorrelationKind,
    CorrelationThresholds,
    DeploymentCorrelationAssessment,
    DeploymentCorrelationThresholds,
    DeploymentEvidence,
    DeploymentEvidenceKind,
    ScoredServiceRelationship,
    ServiceCorrelationResult,
    ServiceCorrelationThresholds,
    ServiceDependencyEdge,
    ServiceRelationshipEvidence,
    ServiceRelationshipKind,
    ServiceRelationshipSignal,
    TemporalCorrelation,
)

__all__ = [
    "CorrelationKind",
    "CorrelationThresholds",
    "DeploymentCorrelationAssessment",
    "DeploymentCorrelationThresholds",
    "DeploymentEvidence",
    "DeploymentEvidenceKind",
    "ScoredServiceRelationship",
    "ServiceCorrelationResult",
    "ServiceCorrelationThresholds",
    "ServiceDependencyEdge",
    "ServiceRelationshipEvidence",
    "ServiceRelationshipKind",
    "ServiceRelationshipSignal",
    "TemporalCorrelation",
    "annotate_metric_anomalies",
    "correlate_service_metric_error",
    "correlate_temporal",
    "correlation_score",
    "correlation_thresholds_from_settings",
    "deployment_correlation_thresholds_from_settings",
    "evaluate_deployment_correlation",
    "infer_dependencies_from_traces",
    "is_error_entry",
    "is_metric_anomaly_entry",
    "service_correlation_thresholds_from_settings",
]
