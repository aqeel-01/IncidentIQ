"""Structured RCA evidence package sent to the AI."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RCAIncidentContext(BaseModel):
    """Incident metadata included in the RCA evidence package."""

    model_config = ConfigDict(frozen=True)

    incident_id: int
    project_id: int
    title: str
    environment: str
    severity: str
    status: str
    service: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    occurrence_count: int = Field(ge=1)


class RCASymptom(BaseModel):
    """Observed symptom such as an alert or log signal."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    timestamp: datetime
    title: str
    severity: str | None = None
    service: str | None = None


class RCAErrorGroupSummary(BaseModel):
    """Condensed error-group evidence."""

    model_config = ConfigDict(frozen=True)

    id: str
    error_group_id: int | None = None
    title: str
    first_seen: datetime
    occurrence_count: int | None = None
    severity: str | None = None
    service: str | None = None


class RCAAnomalySummary(BaseModel):
    """Condensed metric anomaly evidence."""

    model_config = ConfigDict(frozen=True)

    id: str
    timestamp: datetime
    metric_name: str
    value: float | int | str | None = None
    title: str


class RCADeploymentSummary(BaseModel):
    """Condensed deployment evidence."""

    model_config = ConfigDict(frozen=True)

    id: str
    timestamp: datetime
    title: str
    version: str | None = None
    service: str | None = None


class RCATimelineItem(BaseModel):
    """Condensed timeline entry for RCA reasoning."""

    model_config = ConfigDict(frozen=True)

    id: str
    category: str
    timestamp: datetime
    title: str
    severity: str | None = None


class RCACorrelationSummary(BaseModel):
    """Condensed correlation evidence."""

    model_config = ConfigDict(frozen=True)

    kind: str
    source: str
    target: str
    score: float = Field(ge=0.0, le=1.0)
    time_difference_seconds: int | None = None
    reason: str


class RCAEvidenceGraphNodeSummary(BaseModel):
    """Condensed evidence graph node."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    label: str
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)


class RCAEvidenceGraphEdgeSummary(BaseModel):
    """Condensed evidence graph edge."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    target_id: str
    kind: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class RCAEvidenceGraphSummary(BaseModel):
    """Condensed evidence graph for RCA reasoning."""

    model_config = ConfigDict(frozen=True)

    chain: list[str] = Field(default_factory=list)
    nodes: list[RCAEvidenceGraphNodeSummary] = Field(default_factory=list)
    edges: list[RCAEvidenceGraphEdgeSummary] = Field(default_factory=list)
    summary: str


class RCAEvidenceQualitySummary(BaseModel):
    """Condensed evidence quality assessment."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    summary: str
    source_diversity: float = Field(ge=0.0, le=100.0)
    temporal_consistency: float = Field(ge=0.0, le=100.0)
    correlation_strength: float = Field(ge=0.0, le=100.0)
    completeness: float = Field(ge=0.0, le=100.0)
    consistency: float = Field(ge=0.0, le=100.0)


class RCAHistoricalContext(BaseModel):
    """Optional historical incident context."""

    model_config = ConfigDict(frozen=True)

    prior_incident_count: int = Field(default=0, ge=0)
    related_incident_ids: list[int] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RCAEvidencePackage(BaseModel):
    """Exact structured package sent to the RCA engine."""

    model_config = ConfigDict(frozen=True)

    incident: RCAIncidentContext
    symptoms: list[RCASymptom] = Field(default_factory=list)
    error_groups: list[RCAErrorGroupSummary] = Field(default_factory=list)
    anomalies: list[RCAAnomalySummary] = Field(default_factory=list)
    deployments: list[RCADeploymentSummary] = Field(default_factory=list)
    timeline: list[RCATimelineItem] = Field(default_factory=list)
    correlations: list[RCACorrelationSummary] = Field(default_factory=list)
    evidence_graph: RCAEvidenceGraphSummary | None = None
    evidence_quality: RCAEvidenceQualitySummary | None = None
    historical_context: RCAHistoricalContext | None = None
