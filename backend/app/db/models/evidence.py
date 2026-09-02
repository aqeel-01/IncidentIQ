"""Persisted evidence item."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import EvidenceSource, EvidenceStance
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.evidence_group import EvidenceGroup
    from app.db.models.evidence_relation import EvidenceRelation


class Evidence(TimestampMixin, Base):
    """A single structured evidence row within an evidence package."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_group_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[EvidenceSource] = mapped_column(
        Enum(EvidenceSource, native_enum=False, length=40),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("error_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    timeline_entry_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    stance: Mapped[EvidenceStance] = mapped_column(
        Enum(EvidenceStance, native_enum=False, length=20),
        nullable=False,
        index=True,
    )

    evidence_group: Mapped[EvidenceGroup] = relationship(
        back_populates="evidence_items",
    )
    outgoing_relations: Mapped[list[EvidenceRelation]] = relationship(
        foreign_keys="EvidenceRelation.source_evidence_id",
        back_populates="source_evidence",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incoming_relations: Mapped[list[EvidenceRelation]] = relationship(
        foreign_keys="EvidenceRelation.target_evidence_id",
        back_populates="target_evidence",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
