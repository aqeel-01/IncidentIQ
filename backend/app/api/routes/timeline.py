"""Incident timeline API."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import Severity
from app.db.session import get_db
from app.domain.correlation.types import (
    CorrelationKind,
    DeploymentCorrelationAssessment,
    DeploymentEvidence,
    DeploymentEvidenceKind,
    ScoredServiceRelationship,
    ServiceCorrelationResult,
    ServiceDependencyEdge,
    ServiceRelationshipEvidence,
    ServiceRelationshipKind,
    ServiceRelationshipSignal,
    TemporalCorrelation,
)
from app.domain.timeline.service import TimelineService
from app.domain.timeline.types import (
    TimelineCategory,
    TimelineEntry,
    TimelineMarkers,
)

router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class TimelineEntryResponse(BaseModel):
    id: str
    category: TimelineCategory
    timestamp: datetime
    title: str
    summary: str | None = None
    severity: Severity | None = None
    event_id: int | None = None
    error_group_id: int | None = None
    metadata: dict[str, Any]

    model_config = ConfigDict(frozen=True)


class TimelineMarkersResponse(BaseModel):
    first_anomaly: TimelineEntryResponse | None = None
    first_relevant_error: TimelineEntryResponse | None = None
    first_alert: TimelineEntryResponse | None = None
    recent_deployment: TimelineEntryResponse | None = None
    recovery: TimelineEntryResponse | None = None

    model_config = ConfigDict(frozen=True)


class TemporalCorrelationResponse(BaseModel):
    kind: CorrelationKind
    source: TimelineEntryResponse
    target: TimelineEntryResponse
    time_difference: timedelta
    correlation_score: float
    reason: str

    model_config = ConfigDict(frozen=True)


class DeploymentEvidenceResponse(BaseModel):
    kind: DeploymentEvidenceKind
    detail: str
    weight: float

    model_config = ConfigDict(frozen=True)


class DeploymentCorrelationResponse(BaseModel):
    is_related: bool
    relationship_score: float
    deployment: TimelineEntryResponse | None = None
    supporting_evidence: list[DeploymentEvidenceResponse]
    contradicting_evidence: list[DeploymentEvidenceResponse]
    summary: str

    model_config = ConfigDict(frozen=True)


class ServiceRelationshipEvidenceResponse(BaseModel):
    signal: ServiceRelationshipSignal
    detail: str
    weight: float

    model_config = ConfigDict(frozen=True)


class ScoredServiceRelationshipResponse(BaseModel):
    kind: ServiceRelationshipKind
    source_id: str
    source_label: str
    target_id: str
    target_label: str
    correlation_score: float
    evidence: list[ServiceRelationshipEvidenceResponse]
    reason: str
    source_entry_id: str | None = None
    target_entry_id: str | None = None

    model_config = ConfigDict(frozen=True)


class ServiceDependencyEdgeResponse(BaseModel):
    source_service: str
    target_service: str
    inferred_from: str

    model_config = ConfigDict(frozen=True)


class ServiceCorrelationResponse(BaseModel):
    relationships: list[ScoredServiceRelationshipResponse]
    dependencies: list[ServiceDependencyEdgeResponse]
    services: list[str]

    model_config = ConfigDict(frozen=True)


class TimelineResponse(BaseModel):
    incident_id: int
    project_id: int
    started_at: datetime
    ended_at: datetime | None
    window_start: datetime
    window_end: datetime
    entries: list[TimelineEntryResponse]
    markers: TimelineMarkersResponse
    counts: dict[str, int]
    correlations: list[TemporalCorrelationResponse]
    deployment_correlation: DeploymentCorrelationResponse | None = None
    service_correlation: ServiceCorrelationResponse | None = None

    model_config = ConfigDict(frozen=True)


def _entry_response(entry: TimelineEntry | None) -> TimelineEntryResponse | None:
    if entry is None:
        return None
    return TimelineEntryResponse(
        id=entry.id,
        category=entry.category,
        timestamp=entry.timestamp,
        title=entry.title,
        summary=entry.summary,
        severity=entry.severity,
        event_id=entry.event_id,
        error_group_id=entry.error_group_id,
        metadata=entry.metadata,
    )


def _markers_response(markers: TimelineMarkers) -> TimelineMarkersResponse:
    return TimelineMarkersResponse(
        first_anomaly=_entry_response(markers.first_anomaly),
        first_relevant_error=_entry_response(markers.first_relevant_error),
        first_alert=_entry_response(markers.first_alert),
        recent_deployment=_entry_response(markers.recent_deployment),
        recovery=_entry_response(markers.recovery),
    )


def _correlation_response(
    correlation: TemporalCorrelation,
) -> TemporalCorrelationResponse:
    source = _entry_response(correlation.source)
    target = _entry_response(correlation.target)
    assert source is not None
    assert target is not None
    return TemporalCorrelationResponse(
        kind=correlation.kind,
        source=source,
        target=target,
        time_difference=correlation.time_difference,
        correlation_score=correlation.correlation_score,
        reason=correlation.reason,
    )


def _deployment_evidence_response(
    evidence: DeploymentEvidence,
) -> DeploymentEvidenceResponse:
    return DeploymentEvidenceResponse(
        kind=evidence.kind,
        detail=evidence.detail,
        weight=evidence.weight,
    )


def _deployment_correlation_response(
    assessment: DeploymentCorrelationAssessment | None,
) -> DeploymentCorrelationResponse | None:
    if assessment is None:
        return None
    return DeploymentCorrelationResponse(
        is_related=assessment.is_related,
        relationship_score=assessment.relationship_score,
        deployment=_entry_response(assessment.deployment),
        supporting_evidence=[
            _deployment_evidence_response(item)
            for item in assessment.supporting_evidence
        ],
        contradicting_evidence=[
            _deployment_evidence_response(item)
            for item in assessment.contradicting_evidence
        ],
        summary=assessment.summary,
    )


def _service_relationship_evidence_response(
    evidence: ServiceRelationshipEvidence,
) -> ServiceRelationshipEvidenceResponse:
    return ServiceRelationshipEvidenceResponse(
        signal=evidence.signal,
        detail=evidence.detail,
        weight=evidence.weight,
    )


def _scored_service_relationship_response(
    relationship: ScoredServiceRelationship,
) -> ScoredServiceRelationshipResponse:
    return ScoredServiceRelationshipResponse(
        kind=relationship.kind,
        source_id=relationship.source_id,
        source_label=relationship.source_label,
        target_id=relationship.target_id,
        target_label=relationship.target_label,
        correlation_score=relationship.correlation_score,
        evidence=[
            _service_relationship_evidence_response(item)
            for item in relationship.evidence
        ],
        reason=relationship.reason,
        source_entry_id=relationship.source_entry_id,
        target_entry_id=relationship.target_entry_id,
    )


def _service_dependency_response(
    edge: ServiceDependencyEdge,
) -> ServiceDependencyEdgeResponse:
    return ServiceDependencyEdgeResponse(
        source_service=edge.source_service,
        target_service=edge.target_service,
        inferred_from=edge.inferred_from,
    )


def _service_correlation_response(
    result: ServiceCorrelationResult | None,
) -> ServiceCorrelationResponse | None:
    if result is None:
        return None
    return ServiceCorrelationResponse(
        relationships=[
            _scored_service_relationship_response(item)
            for item in result.relationships
        ],
        dependencies=[
            _service_dependency_response(item) for item in result.dependencies
        ],
        services=result.services,
    )


@router.get("/{incident_id}", response_model=TimelineResponse)
async def get_incident_timeline(
    incident_id: int,
    session: SessionDep,
) -> TimelineResponse:
    result = await TimelineService(session).build(incident_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident {incident_id} not found",
        )

    return TimelineResponse(
        incident_id=result.incident_id,
        project_id=result.project_id,
        started_at=result.started_at,
        ended_at=result.ended_at,
        window_start=result.window_start,
        window_end=result.window_end,
        entries=[
            entry
            for entry in (
                _entry_response(item) for item in result.entries
            )
            if entry is not None
        ],
        markers=_markers_response(result.markers),
        counts=result.counts,
        correlations=[
            _correlation_response(item) for item in result.correlations
        ],
        deployment_correlation=_deployment_correlation_response(
            result.deployment_correlation,
        ),
        service_correlation=_service_correlation_response(
            result.service_correlation,
        ),
    )
