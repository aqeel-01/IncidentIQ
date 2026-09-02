"""Incident: a tracked production problem under investigation."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import IncidentStatus, Severity
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.project import Project
    from app.db.models.service import Service


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_project_status", "project_id", "status"),
        Index("ix_incidents_project_started_at", "project_id", "started_at"),
        Index("ix_incidents_project_fingerprint", "project_id", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # An incident is usually attributed to one service; kept nullable so an
    # incident can exist before attribution or span multiple services.
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False, length=20),
        nullable=False,
        default=IncidentStatus.OPEN,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    project: Mapped[Project] = relationship(back_populates="incidents")
    service: Mapped[Service | None] = relationship(back_populates="incidents")
