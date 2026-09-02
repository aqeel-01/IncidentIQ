"""Persisted evidence package for an incident investigation."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.evidence import Evidence
    from app.db.models.evidence_relation import EvidenceRelation
    from app.db.models.incident import Incident
    from app.db.models.project import Project


class EvidenceGroup(TimestampMixin, Base):
    """Container for a structured evidence package tied to an incident."""

    __tablename__ = "evidence_groups"
    __table_args__ = (
        Index("ix_evidence_groups_incident_built_at", "incident_id", "built_at"),
        Index("ix_evidence_groups_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quality_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    incident: Mapped[Incident] = relationship()
    project: Mapped[Project] = relationship()
    evidence_items: Mapped[list[Evidence]] = relationship(
        back_populates="evidence_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    relations: Mapped[list[EvidenceRelation]] = relationship(
        back_populates="evidence_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
