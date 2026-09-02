"""ErrorGroup: deduplicated set of equivalent errors (see SRS §6)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import Severity
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.error_group_similarity_candidate import (
        ErrorGroupSimilarityCandidate,
    )
    from app.db.models.event import Event
    from app.db.models.project import Project
    from app.db.models.service import Service


class ErrorGroup(TimestampMixin, Base):
    __tablename__ = "error_groups"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "fingerprint", name="uq_error_groups_project_fingerprint"
        ),
        Index("ix_error_groups_project_last_seen", "project_id", "last_seen"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_message: Mapped[str] = mapped_column(Text, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, length=20),
        nullable=False,
        index=True,
    )

    project: Mapped[Project] = relationship(back_populates="error_groups")
    service: Mapped[Service | None] = relationship(back_populates="error_groups")
    events: Mapped[list[Event]] = relationship(back_populates="error_group")
    similarity_candidates_as_source: Mapped[list[ErrorGroupSimilarityCandidate]] = (
        relationship(
            foreign_keys="ErrorGroupSimilarityCandidate.source_error_group_id",
            back_populates="source_error_group",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )
    )
    similarity_candidates_as_candidate: Mapped[list[ErrorGroupSimilarityCandidate]] = (
        relationship(
            foreign_keys="ErrorGroupSimilarityCandidate.candidate_error_group_id",
            back_populates="candidate_error_group",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )
    )
