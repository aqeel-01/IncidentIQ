"""Log upload job tracking."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.project import Project


class LogUploadStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LogUpload(TimestampMixin, Base):
    """Metadata for an uploaded log file awaiting or after processing."""

    __tablename__ = "log_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        nullable=False,
    )
    status: Mapped[LogUploadStatus] = mapped_column(
        Enum(LogUploadStatus, native_enum=False, length=20),
        nullable=False,
        default=LogUploadStatus.QUEUED,
        index=True,
    )

    project: Mapped[Project] = relationship(back_populates="log_uploads")
