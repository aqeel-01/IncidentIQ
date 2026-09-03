"""Project: a unit of work within an organization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.configured_connector import ConfiguredConnector
    from app.db.models.error_group import ErrorGroup
    from app.db.models.event import Event
    from app.db.models.incident import Incident
    from app.db.models.log_upload import LogUpload
    from app.db.models.organization import Organization
    from app.db.models.project_membership import ProjectMembership
    from app.db.models.service import Service


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="projects")
    memberships: Mapped[list[ProjectMembership]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    services: Mapped[list[Service]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    incidents: Mapped[list[Incident]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list[Event]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    error_groups: Mapped[list[ErrorGroup]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    log_uploads: Mapped[list[LogUpload]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    connectors: Mapped[list[ConfiguredConnector]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
