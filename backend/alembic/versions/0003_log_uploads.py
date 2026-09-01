"""core log upload jobs

Revision ID: 0003_log_uploads
Revises: 0002_core_models
Create Date: 2026-09-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_log_uploads"
down_revision: str | None = "0002_core_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "log_uploads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("file_extension", sa.String(length=10), nullable=False),
        sa.Column("content_type", sa.String(length=127), nullable=True),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="loguploadstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_log_uploads_project_id"), "log_uploads", ["project_id"])
    op.create_index(op.f("ix_log_uploads_status"), "log_uploads", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_log_uploads_status"), table_name="log_uploads")
    op.drop_index(op.f("ix_log_uploads_project_id"), table_name="log_uploads")
    op.drop_table("log_uploads")
