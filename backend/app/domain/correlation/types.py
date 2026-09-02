"""Temporal correlation types."""

from __future__ import annotations

import enum
from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.timeline.types import TimelineEntry


class CorrelationKind(enum.StrEnum):
    """Supported temporal relationship between incident events."""

    DEPLOYMENT_TO_ERROR = "deployment_to_error"
    METRIC_ANOMALY_TO_ERROR = "metric_anomaly_to_error"
    ERROR_TO_ALERT = "error_to_alert"


class CorrelationThresholds(BaseModel):
    """Configurable limits for temporal correlation."""

    model_config = ConfigDict(frozen=True)

    deployment_to_error_max_lag: timedelta = Field(
        default=timedelta(hours=2),
    )
    metric_anomaly_to_error_max_lag: timedelta = Field(
        default=timedelta(minutes=30),
    )
    error_to_alert_max_lag: timedelta = Field(
        default=timedelta(minutes=15),
    )
    min_score: float = Field(default=0.1, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_lags(self) -> CorrelationThresholds:
        for name in (
            "deployment_to_error_max_lag",
            "metric_anomaly_to_error_max_lag",
            "error_to_alert_max_lag",
        ):
            lag = getattr(self, name)
            if lag.total_seconds() <= 0:
                msg = f"{name} must be positive"
                raise ValueError(msg)
        return self


class TemporalCorrelation(BaseModel):
    """A deterministic temporal link between two timeline events."""

    model_config = ConfigDict(frozen=True)

    kind: CorrelationKind
    source: TimelineEntry
    target: TimelineEntry
    time_difference: timedelta
    correlation_score: float = Field(ge=0.0, le=1.0)
    reason: str


class DeploymentEvidenceKind(enum.StrEnum):
    """Kinds of deployment-correlation evidence."""

    RECENT_DEPLOYMENT = "recent_deployment"
    DEPLOYMENT_BEFORE_FIRST_ERROR = "deployment_before_first_error"
    DEPLOYMENT_BEFORE_FIRST_ANOMALY = "deployment_before_first_anomaly"
    DEPLOYMENT_ERROR_TEMPORAL_LINK = "deployment_error_temporal_link"
    AFFECTED_SERVICE_MATCH = "affected_service_match"
    CHANGED_COMPONENT_OVERLAP = "changed_component_overlap"
    NO_RECENT_DEPLOYMENT = "no_recent_deployment"
    FIRST_ERROR_BEFORE_DEPLOYMENT = "first_error_before_deployment"
    FIRST_ANOMALY_BEFORE_DEPLOYMENT = "first_anomaly_before_deployment"
    DEPLOYMENT_AFTER_INCIDENT_START = "deployment_after_incident_start"
    MISSING_DEPLOYMENT_ERROR_LINK = "missing_deployment_error_link"
    AFFECTED_SERVICE_MISMATCH = "affected_service_mismatch"
    DEPLOYMENT_ALONE_INSUFFICIENT = "deployment_alone_insufficient"


class DeploymentEvidence(BaseModel):
    """A single supporting or contradicting deployment signal."""

    model_config = ConfigDict(frozen=True)

    kind: DeploymentEvidenceKind
    detail: str
    weight: float = Field(default=0.2, ge=0.0, le=1.0)


class DeploymentCorrelationThresholds(BaseModel):
    """Configurable thresholds for deployment correlation."""

    model_config = ConfigDict(frozen=True)

    deployment_lookback: timedelta = Field(default=timedelta(hours=24))
    deployment_to_error_max_lag: timedelta = Field(default=timedelta(hours=2))
    min_relationship_score: float = Field(default=0.4, ge=0.0, le=1.0)


class DeploymentCorrelationAssessment(BaseModel):
    """Assessment of whether an incident relates to a recent deployment."""

    model_config = ConfigDict(frozen=True)

    is_related: bool
    relationship_score: float = Field(ge=0.0, le=1.0)
    deployment: TimelineEntry | None = None
    supporting_evidence: list[DeploymentEvidence] = Field(default_factory=list)
    contradicting_evidence: list[DeploymentEvidence] = Field(default_factory=list)
    summary: str


class ServiceRelationshipKind(enum.StrEnum):
    """Scored relationships between services, metrics, errors, and traces."""

    METRIC_ANOMALY_TO_ERROR = "metric_anomaly_to_error"
    METRIC_ANOMALY_TO_SERVICE = "metric_anomaly_to_service"
    ERROR_TO_SERVICE = "error_to_service"
    TRACE_TO_ERROR = "trace_to_error"
    SERVICE_DEPENDENCY = "service_dependency"
    UPSTREAM_ERROR_PROPAGATION = "upstream_error_propagation"


class ServiceRelationshipSignal(enum.StrEnum):
    """Structured signals used to score service relationships."""

    TEMPORAL_PROXIMITY = "temporal_proximity"
    SAME_SERVICE = "same_service"
    SHARED_TRACE = "shared_trace"
    DEPENDENCY_EDGE = "dependency_edge"
    SERVICE_ATTRIBUTION = "service_attribution"


class ServiceRelationshipEvidence(BaseModel):
    """A single deterministic signal contributing to a relationship score."""

    model_config = ConfigDict(frozen=True)

    signal: ServiceRelationshipSignal
    detail: str
    weight: float = Field(default=0.2, ge=0.0, le=1.0)


class ServiceDependencyEdge(BaseModel):
    """A directed dependency between two services."""

    model_config = ConfigDict(frozen=True)

    source_service: str
    target_service: str
    inferred_from: str = "trace"


class ScoredServiceRelationship(BaseModel):
    """A scored relationship with structured evidence."""

    model_config = ConfigDict(frozen=True)

    kind: ServiceRelationshipKind
    source_id: str
    source_label: str
    target_id: str
    target_label: str
    correlation_score: float = Field(ge=0.0, le=1.0)
    evidence: list[ServiceRelationshipEvidence]
    reason: str
    source_entry_id: str | None = None
    target_entry_id: str | None = None


class ServiceCorrelationThresholds(BaseModel):
    """Configurable thresholds for service and metric/error correlation."""

    model_config = ConfigDict(frozen=True)

    metric_anomaly_to_error_max_lag: timedelta = Field(
        default=timedelta(minutes=30),
    )
    trace_to_error_max_lag: timedelta = Field(default=timedelta(minutes=5))
    upstream_propagation_max_lag: timedelta = Field(default=timedelta(minutes=15))
    min_score: float = Field(default=0.2, ge=0.0, le=1.0)
    same_service_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    temporal_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    dependency_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    trace_weight: float = Field(default=0.3, ge=0.0, le=1.0)


class ServiceCorrelationResult(BaseModel):
    """Structured output from service and metric/error correlation."""

    model_config = ConfigDict(frozen=True)

    relationships: list[ScoredServiceRelationship] = Field(default_factory=list)
    dependencies: list[ServiceDependencyEdge] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
