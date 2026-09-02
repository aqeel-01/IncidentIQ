"""Incident evidence API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.evidence import EvidenceService
from app.domain.evidence.types import (
    EventReference,
    Evidence,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphEdgeKind,
    EvidenceGraphNode,
    EvidenceGraphNodeKind,
    EvidenceGroup,
    EvidenceQualityAssessment,
    EvidenceRelation,
    EvidenceRelationKind,
    EvidenceSource,
    EvidenceStance,
)
from app.domain.timeline.service import TimelineService

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class EventReferenceResponse(BaseModel):
    event_id: int | None = None
    error_group_id: int | None = None
    timeline_entry_id: str | None = None

    model_config = ConfigDict(frozen=True)


class EvidenceResponse(BaseModel):
    key: str
    source: EvidenceSource
    timestamp: datetime
    event_reference: EventReferenceResponse
    description: str
    value: str | float | int | bool | None = None
    confidence: float
    supporting_or_contradicting: EvidenceStance

    model_config = ConfigDict(frozen=True)


class EvidenceRelationResponse(BaseModel):
    key: str
    source_evidence_key: str
    target_evidence_key: str
    kind: EvidenceRelationKind
    confidence: float
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class EvidenceGraphNodeResponse(BaseModel):
    id: str
    kind: EvidenceGraphNodeKind
    label: str
    timestamp: datetime
    event_reference: EventReferenceResponse
    confidence: float
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class EvidenceGraphEdgeResponse(BaseModel):
    key: str
    source_id: str
    target_id: str
    kind: EvidenceGraphEdgeKind
    confidence: float
    reason: str

    model_config = ConfigDict(frozen=True)


class EvidenceGraphResponse(BaseModel):
    incident_id: int
    project_id: int
    nodes: list[EvidenceGraphNodeResponse]
    edges: list[EvidenceGraphEdgeResponse]
    chain: list[str]
    summary: str

    model_config = ConfigDict(frozen=True)


class EvidenceQualityBreakdownResponse(BaseModel):
    source_diversity: float
    temporal_consistency: float
    correlation_strength: float
    completeness: float
    consistency: float

    model_config = ConfigDict(frozen=True)


class EvidenceQualityResponse(BaseModel):
    score: int
    breakdown: EvidenceQualityBreakdownResponse
    summary: str

    model_config = ConfigDict(frozen=True)


class EvidenceGroupResponse(BaseModel):
    id: int | None
    incident_id: int
    project_id: int
    built_at: datetime
    engine_version: str
    summary: str | None
    evidence: list[EvidenceResponse]
    relations: list[EvidenceRelationResponse]
    evidence_graph: EvidenceGraphResponse | None = None
    quality: EvidenceQualityResponse | None = None
    metadata: dict[str, Any]

    model_config = ConfigDict(frozen=True)


def _event_reference_response(
    reference: EventReference,
) -> EventReferenceResponse:
    return EventReferenceResponse(
        event_id=reference.event_id,
        error_group_id=reference.error_group_id,
        timeline_entry_id=reference.timeline_entry_id,
    )


def _evidence_response(item: Evidence) -> EvidenceResponse:
    return EvidenceResponse(
        key=item.key,
        source=item.source,
        timestamp=item.timestamp,
        event_reference=_event_reference_response(item.event_reference),
        description=item.description,
        value=item.value,
        confidence=item.confidence,
        supporting_or_contradicting=item.supporting_or_contradicting,
    )


def _relation_response(item: EvidenceRelation) -> EvidenceRelationResponse:
    return EvidenceRelationResponse(
        key=item.key,
        source_evidence_key=item.source_evidence_key,
        target_evidence_key=item.target_evidence_key,
        kind=item.kind,
        confidence=item.confidence,
        description=item.description,
    )


def _graph_node_response(node: EvidenceGraphNode) -> EvidenceGraphNodeResponse:
    return EvidenceGraphNodeResponse(
        id=node.id,
        kind=node.kind,
        label=node.label,
        timestamp=node.timestamp,
        event_reference=_event_reference_response(node.event_reference),
        confidence=node.confidence,
        description=node.description,
    )


def _graph_edge_response(edge: EvidenceGraphEdge) -> EvidenceGraphEdgeResponse:
    return EvidenceGraphEdgeResponse(
        key=edge.key,
        source_id=edge.source_id,
        target_id=edge.target_id,
        kind=edge.kind,
        confidence=edge.confidence,
        reason=edge.reason,
    )


def _evidence_graph_response(graph: EvidenceGraph) -> EvidenceGraphResponse:
    return EvidenceGraphResponse(
        incident_id=graph.incident_id,
        project_id=graph.project_id,
        nodes=[_graph_node_response(node) for node in graph.nodes],
        edges=[_graph_edge_response(edge) for edge in graph.edges],
        chain=graph.chain,
        summary=graph.summary,
    )


def _quality_response(quality: EvidenceQualityAssessment) -> EvidenceQualityResponse:
    return EvidenceQualityResponse(
        score=quality.score,
        breakdown=EvidenceQualityBreakdownResponse(
            source_diversity=quality.breakdown.source_diversity,
            temporal_consistency=quality.breakdown.temporal_consistency,
            correlation_strength=quality.breakdown.correlation_strength,
            completeness=quality.breakdown.completeness,
            consistency=quality.breakdown.consistency,
        ),
        summary=quality.summary,
    )


def _evidence_group_response(group: EvidenceGroup) -> EvidenceGroupResponse:
    return EvidenceGroupResponse(
        id=group.id,
        incident_id=group.incident_id,
        project_id=group.project_id,
        built_at=group.built_at,
        engine_version=group.engine_version,
        summary=group.summary,
        evidence=[_evidence_response(item) for item in group.evidence],
        relations=[_relation_response(item) for item in group.relations],
        evidence_graph=(
            _evidence_graph_response(group.evidence_graph)
            if group.evidence_graph is not None
            else None
        ),
        quality=(
            _quality_response(group.quality) if group.quality is not None else None
        ),
        metadata=group.metadata,
    )


@router.get("/{incident_id}", response_model=EvidenceGroupResponse)
async def get_incident_evidence(
    incident_id: int,
    session: SessionDep,
) -> EvidenceGroupResponse:
    existing = await EvidenceService(session).get_latest_for_incident(incident_id)
    if existing is not None:
        return _evidence_group_response(existing)

    timeline = await TimelineService(session).build(incident_id)
    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"incident {incident_id} not found",
        )
    if timeline.evidence_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"evidence for incident {incident_id} not found",
        )
    await session.commit()
    return _evidence_group_response(timeline.evidence_group)
