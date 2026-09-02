"""Persisted root cause analysis results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.evidence_group import EvidenceGroup
    from app.db.models.incident import Incident
    from app.db.models.investigation_job import InvestigationJob
    from app.db.models.project import Project


class RCAResultRecord(TimestampMixin, Base):
    """Structured RCA output persisted for an incident investigation."""

    __tablename__ = "rca_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    investigation_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigation_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_quality: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(120), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    result_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    project: Mapped[Project] = relationship()
    incident: Mapped[Incident] = relationship()
    investigation_job: Mapped[InvestigationJob | None] = relationship(
        foreign_keys=[investigation_job_id],
        back_populates="historical_rca_results",
    )
    evidence_group: Mapped[EvidenceGroup | None] = relationship()
