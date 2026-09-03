"""Project membership: links a user to a project with a role."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import ProjectRole
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.project import Project
    from app.db.models.user import User


class ProjectMembership(TimestampMixin, Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            name="uq_project_memberships_user_project",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, native_enum=False, length=20),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    project: Mapped[Project] = relationship(back_populates="memberships")
