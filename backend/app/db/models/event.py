"""Event: a canonical, source-agnostic record (see SRS §4).

A single table holds all canonical event categories, discriminated by
``event_type``. Raw and normalized payloads are preserved for traceability.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import EventType, Severity

if TYPE_CHECKING:
    from app.db.models.error_group import ErrorGroup
    from app.db.models.project import Project
    from app.db.models.service import Service


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_project_timestamp", "project_id", "timestamp"),
        Index("ix_events_error_group_timestamp", "error_group_id", "timestamp"),
    )

    # BigInteger for high-volume ingestion; falls back to INTEGER on SQLite so
    # autoincrement works in tests.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
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
    error_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("error_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[Severity | None] = mapped_column(
        Enum(Severity, native_enum=False, length=20), nullable=True
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="events")
    service: Mapped[Service | None] = relationship(back_populates="events")
    error_group: Mapped[ErrorGroup | None] = relationship(back_populates="events")
