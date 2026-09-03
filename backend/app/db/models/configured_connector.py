"""Persisted connector configurations for a project."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.project import Project


class ConfiguredConnector(TimestampMixin, Base):
    """A project-scoped connector configuration with encrypted credentials."""

    __tablename__ = "configured_connectors"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "name",
            name="uq_configured_connectors_project_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_test_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="connectors")
