"""Persisted possible-match links between error groups for investigation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.error_group import ErrorGroup
    from app.db.models.project import Project


class ErrorGroupSimilarityCandidate(TimestampMixin, Base):
    """A possible-match link kept for review without merging groups."""

    __tablename__ = "error_group_similarity_candidates"
    __table_args__ = (
        UniqueConstraint(
            "source_error_group_id",
            "candidate_error_group_id",
            name="uq_error_group_similarity_candidate_pair",
        ),
        Index(
            "ix_error_group_similarity_candidates_project",
            "project_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_error_group_id: Mapped[int] = mapped_column(
        ForeignKey("error_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_error_group_id: Mapped[int] = mapped_column(
        ForeignKey("error_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)

    project: Mapped[Project] = relationship()
    source_error_group: Mapped[ErrorGroup] = relationship(
        foreign_keys=[source_error_group_id],
        back_populates="similarity_candidates_as_source",
    )
    candidate_error_group: Mapped[ErrorGroup] = relationship(
        foreign_keys=[candidate_error_group_id],
        back_populates="similarity_candidates_as_candidate",
    )
