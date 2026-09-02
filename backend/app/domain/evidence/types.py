"""Structured evidence models."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceSource(enum.StrEnum):
    """Origin of a piece of incident evidence."""

    ANOMALY_DETECTION = "anomaly_detection"
    TEMPORAL_CORRELATION = "temporal_correlation"
    DEPLOYMENT_CORRELATION = "deployment_correlation"
    SERVICE_CORRELATION = "service_correlation"
    TIMELINE_MARKER = "timeline_marker"


class EvidenceStance(enum.StrEnum):
    """Whether evidence supports or contradicts a hypothesis."""

    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"


class EvidenceRelationKind(enum.StrEnum):
    """Relationship between two evidence items."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CORRELATES_WITH = "correlates_with"
    CAUSED_BY = "caused_by"
    RELATED_TO = "related_to"


class EventReference(BaseModel):
    """Reference to an underlying timeline or persisted event."""

    model_config = ConfigDict(frozen=True)

    event_id: int | None = None
    error_group_id: int | None = None
    timeline_entry_id: str | None = None


class Evidence(BaseModel):
    """A single structured evidence item."""

    model_config = ConfigDict(frozen=True)

    key: str
    source: EvidenceSource
    timestamp: datetime
    event_reference: EventReference = Field(default_factory=EventReference)
    description: str
    value: str | float | int | bool | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_or_contradicting: EvidenceStance

    @field_validator("timestamp")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EvidenceRelation(BaseModel):
    """A directed relationship between two evidence items."""

    model_config = ConfigDict(frozen=True)

    key: str
    source_evidence_key: str
    target_evidence_key: str
    kind: EvidenceRelationKind
    confidence: float = Field(ge=0.0, le=1.0)
    description: str | None = None


class EvidenceGroup(BaseModel):
    """A structured evidence package for an incident investigation."""

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    incident_id: int
    project_id: int
    built_at: datetime
    engine_version: str = "1.0"
    summary: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    relations: list[EvidenceRelation] = Field(default_factory=list)
    evidence_graph: EvidenceGraph | None = None
    quality: EvidenceQualityAssessment | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("built_at")
    @classmethod
    def _normalize_built_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EvidenceGraphNodeKind(enum.StrEnum):
    """Canonical node kinds in the incident evidence graph."""

    DEPLOYMENT = "deployment"
    METRIC_ANOMALY = "metric_anomaly"
    ERROR_INCREASE = "error_increase"
    SERVICE_FAILURE = "service_failure"
    INCIDENT = "incident"


class EvidenceGraphEdgeKind(enum.StrEnum):
    """Directed relationships between evidence graph nodes."""

    LEADS_TO = "leads_to"
    CORRELATES_WITH = "correlates_with"
    ESCALATED_TO = "escalated_to"


class EvidenceGraphNode(BaseModel):
    """A node in the incident evidence graph."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: EvidenceGraphNodeKind
    label: str
    timestamp: datetime
    event_reference: EventReference = Field(default_factory=EventReference)
    confidence: float = Field(ge=0.0, le=1.0)
    description: str | None = None

    @field_validator("timestamp")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EvidenceGraphEdge(BaseModel):
    """A directed edge in the incident evidence graph."""

    model_config = ConfigDict(frozen=True)

    key: str
    source_id: str
    target_id: str
    kind: EvidenceGraphEdgeKind
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class EvidenceGraph(BaseModel):
    """Evidence graph combining timeline and correlation results."""

    model_config = ConfigDict(frozen=True)

    incident_id: int
    project_id: int
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    chain: list[str] = Field(default_factory=list)
    summary: str


class EvidenceQualityBreakdown(BaseModel):
    """Per-dimension evidence quality scores on a 0-100 scale."""

    model_config = ConfigDict(frozen=True)

    source_diversity: float = Field(ge=0.0, le=100.0)
    temporal_consistency: float = Field(ge=0.0, le=100.0)
    correlation_strength: float = Field(ge=0.0, le=100.0)
    completeness: float = Field(ge=0.0, le=100.0)
    consistency: float = Field(ge=0.0, le=100.0)


class EvidenceQualityAssessment(BaseModel):
    """Overall evidence quality assessment for an incident package."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    breakdown: EvidenceQualityBreakdown
    summary: str
