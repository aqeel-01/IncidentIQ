"""Structured incident evidence engine."""

from app.domain.evidence.engine import build_evidence_group
from app.domain.evidence.graph import build_evidence_graph
from app.domain.evidence.quality import score_evidence_quality
from app.domain.evidence.service import EvidenceService
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
    EvidenceQualityBreakdown,
    EvidenceRelation,
    EvidenceRelationKind,
    EvidenceSource,
    EvidenceStance,
)

__all__ = [
    "Evidence",
    "EvidenceGraph",
    "EvidenceGraphEdge",
    "EvidenceGraphEdgeKind",
    "EvidenceGraphNode",
    "EvidenceGraphNodeKind",
    "EvidenceGroup",
    "EvidenceQualityAssessment",
    "EvidenceQualityBreakdown",
    "EvidenceRelation",
    "EvidenceRelationKind",
    "EvidenceService",
    "EvidenceSource",
    "EvidenceStance",
    "EventReference",
    "build_evidence_graph",
    "build_evidence_group",
    "score_evidence_quality",
]
