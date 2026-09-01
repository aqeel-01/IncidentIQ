"""Service: a deployable component within a project."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.error_group import ErrorGroup
    from app.db.models.event import Event
    from app.db.models.incident import Incident
    from app.db.models.project import Project


class Service(TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_services_project_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    project: Mapped[Project] = relationship(back_populates="services")
    incidents: Mapped[list[Incident]] = relationship(back_populates="service")
    events: Mapped[list[Event]] = relationship(back_populates="service")
    error_groups: Mapped[list[ErrorGroup]] = relationship(back_populates="service")
