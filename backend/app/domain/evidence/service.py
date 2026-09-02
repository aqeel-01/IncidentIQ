"""Evidence persistence and retrieval service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.enums import EvidenceRelationKind as DbEvidenceRelationKind
from app.db.models.enums import EvidenceSource as DbEvidenceSource
from app.db.models.enums import EvidenceStance as DbEvidenceStance
from app.db.models.evidence import Evidence as EvidenceRow
from app.db.models.evidence_group import EvidenceGroup as EvidenceGroupRow
from app.db.models.evidence_relation import EvidenceRelation as EvidenceRelationRow
from app.domain.evidence.engine import build_evidence_group
from app.domain.evidence.types import (
    EventReference,
    Evidence,
    EvidenceGraph,
    EvidenceGroup,
    EvidenceQualityAssessment,
    EvidenceRelation,
    EvidenceRelationKind,
    EvidenceSource,
    EvidenceStance,
)
from app.domain.timeline.types import TimelineResult


class EvidenceService:
    """Build and persist structured evidence packages for incidents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build_from_timeline(
        self,
        timeline: TimelineResult,
        *,
        service_names: dict[int, str] | None = None,
        affected_service: str | None = None,
    ) -> EvidenceGroup:
        """Build and persist an evidence package from a timeline result."""

        package = build_evidence_group(
            timeline,
            service_names=service_names,
            affected_service=affected_service,
        )
        return await self.persist(package)

    async def persist(self, package: EvidenceGroup) -> EvidenceGroup:
        """Persist a structured evidence package."""

        group_row = EvidenceGroupRow(
            incident_id=package.incident_id,
            project_id=package.project_id,
            built_at=package.built_at,
            engine_version=package.engine_version,
            summary=package.summary,
            graph_data=(
                package.evidence_graph.model_dump(mode="json")
                if package.evidence_graph is not None
                else None
            ),
            quality_data=(
                package.quality.model_dump(mode="json")
                if package.quality is not None
                else None
            ),
        )
        self._session.add(group_row)
        await self._session.flush()

        key_to_id: dict[str, int] = {}
        for item in package.evidence:
            row = EvidenceRow(
                evidence_group_id=group_row.id,
                evidence_key=item.key,
                source=DbEvidenceSource(item.source.value),
                timestamp=item.timestamp,
                event_id=item.event_reference.event_id,
                error_group_id=item.event_reference.error_group_id,
                timeline_entry_id=item.event_reference.timeline_entry_id,
                description=item.description,
                value=item.value,
                confidence=item.confidence,
                stance=DbEvidenceStance(item.supporting_or_contradicting.value),
            )
            self._session.add(row)
            await self._session.flush()
            key_to_id[item.key] = row.id

        for relation in package.relations:
            self._session.add(
                EvidenceRelationRow(
                    evidence_group_id=group_row.id,
                    relation_key=relation.key,
                    source_evidence_id=key_to_id[relation.source_evidence_key],
                    target_evidence_id=key_to_id[relation.target_evidence_key],
                    kind=DbEvidenceRelationKind(relation.kind.value),
                    confidence=relation.confidence,
                    description=relation.description,
                )
            )

        await self._session.flush()
        return await self.get_by_id(group_row.id)

    async def get_latest_for_incident(self, incident_id: int) -> EvidenceGroup | None:
        result = await self._session.execute(
            select(EvidenceGroupRow)
            .where(EvidenceGroupRow.incident_id == incident_id)
            .order_by(EvidenceGroupRow.built_at.desc())
            .limit(1)
            .options(
                selectinload(EvidenceGroupRow.evidence_items),
                selectinload(EvidenceGroupRow.relations),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_domain(row)

    async def get_by_id(self, evidence_group_id: int) -> EvidenceGroup:
        result = await self._session.execute(
            select(EvidenceGroupRow)
            .where(EvidenceGroupRow.id == evidence_group_id)
            .options(
                selectinload(EvidenceGroupRow.evidence_items),
                selectinload(EvidenceGroupRow.relations),
            )
        )
        row = result.scalar_one()
        return _to_domain(row)


def _to_domain(row: EvidenceGroupRow) -> EvidenceGroup:
    evidence_rows = sorted(row.evidence_items, key=lambda item: item.id)
    id_to_key = {item.id: item.evidence_key for item in evidence_rows}
    return EvidenceGroup(
        id=row.id,
        incident_id=row.incident_id,
        project_id=row.project_id,
        built_at=row.built_at,
        engine_version=row.engine_version,
        summary=row.summary,
        evidence=[_evidence_to_domain(item) for item in evidence_rows],
        relations=[
            EvidenceRelation(
                key=relation.relation_key,
                source_evidence_key=id_to_key[relation.source_evidence_id],
                target_evidence_key=id_to_key[relation.target_evidence_id],
                kind=EvidenceRelationKind(relation.kind.value),
                confidence=relation.confidence,
                description=relation.description,
            )
            for relation in sorted(row.relations, key=lambda item: item.id)
        ],
        evidence_graph=(
            EvidenceGraph.model_validate(row.graph_data)
            if row.graph_data is not None
            else None
        ),
        quality=(
            EvidenceQualityAssessment.model_validate(row.quality_data)
            if row.quality_data is not None
            else None
        ),
        metadata={
            "evidence_count": len(evidence_rows),
            "relation_count": len(row.relations),
            "graph_node_count": (
                len(row.graph_data.get("nodes", [])) if row.graph_data else 0
            ),
            "graph_edge_count": (
                len(row.graph_data.get("edges", [])) if row.graph_data else 0
            ),
            "quality_score": (
                row.quality_data.get("score") if row.quality_data is not None else None
            ),
        },
    )


def _evidence_to_domain(row: EvidenceRow) -> Evidence:
    return Evidence(
        key=row.evidence_key,
        source=EvidenceSource(row.source.value),
        timestamp=row.timestamp,
        event_reference=EventReference(
            event_id=row.event_id,
            error_group_id=row.error_group_id,
            timeline_entry_id=row.timeline_entry_id,
        ),
        description=row.description,
        value=row.value,
        confidence=row.confidence,
        supporting_or_contradicting=EvidenceStance(row.stance.value),
    )
