"""Investigation background job tracking."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.incident import Incident
    from app.db.models.project import Project
    from app.db.models.rca_result import RCAResultRecord


class InvestigationJobStatus(enum.StrEnum):
    """Lifecycle status for an investigation background job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InvestigationStage(enum.StrEnum):
    """Current pipeline stage for an investigation job."""

    QUEUED = "queued"
    COLLECT_SOURCES = "collect_sources"
    PARSE = "parse"
    NORMALIZE = "normalize"
    DEDUPLICATE = "dedupe"
    GROUP_ERRORS = "group_errors"
    DETECT_ANOMALIES = "anomalies"
    BUILD_TIMELINE = "timeline"
    CORRELATE = "correlate"
    BUILD_EVIDENCE = "evidence"
    CALCULATE_EVIDENCE_QUALITY = "quality"
    BUILD_RCA_PACKAGE = "rca_package"
    RUN_RCA = "run_rca"
    PERSIST_RCA = "persist_rca"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationJob(TimestampMixin, Base):
    """Persisted investigation job submitted for background processing."""

    __tablename__ = "investigation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
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
    status: Mapped[InvestigationJobStatus] = mapped_column(
        Enum(InvestigationJobStatus, native_enum=False, length=20),
        nullable=False,
        default=InvestigationJobStatus.QUEUED,
        index=True,
    )
    stage: Mapped[InvestigationStage] = mapped_column(
        Enum(InvestigationStage, native_enum=False, length=32),
        nullable=False,
        default=InvestigationStage.QUEUED,
        index=True,
    )
    stage_artifacts: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rca_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("rca_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    project: Mapped[Project] = relationship()
    incident: Mapped[Incident] = relationship()
    rca_result: Mapped[RCAResultRecord | None] = relationship(
        foreign_keys=[rca_result_id],
    )
    historical_rca_results: Mapped[list[RCAResultRecord]] = relationship(
        foreign_keys="RCAResultRecord.investigation_job_id",
        back_populates="investigation_job",
    )
