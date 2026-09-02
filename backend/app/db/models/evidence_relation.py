"""Persisted relationship between evidence items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import EvidenceRelationKind
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.evidence import Evidence
    from app.db.models.evidence_group import EvidenceGroup


class EvidenceRelation(TimestampMixin, Base):
    """Directed link between two evidence rows in the same package."""

    __tablename__ = "evidence_relations"
    __table_args__ = (
        UniqueConstraint(
            "evidence_group_id",
            "relation_key",
            name="uq_evidence_relations_group_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_group_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[EvidenceRelationKind] = mapped_column(
        Enum(EvidenceRelationKind, native_enum=False, length=32),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_group: Mapped[EvidenceGroup] = relationship(back_populates="relations")
    source_evidence: Mapped[Evidence] = relationship(
        foreign_keys=[source_evidence_id],
        back_populates="outgoing_relations",
    )
    target_evidence: Mapped[Evidence] = relationship(
        foreign_keys=[target_evidence_id],
        back_populates="incoming_relations",
    )
