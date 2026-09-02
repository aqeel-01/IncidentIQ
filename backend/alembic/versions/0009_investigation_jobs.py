"""investigation background jobs

Revision ID: 0009_investigation_jobs
Revises: 0008_evidence_quality
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_investigation_jobs"
down_revision: str | None = "0008_evidence_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigation_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "RETRYING",
                "COMPLETED",
                "FAILED",
                name="investigationjobstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "stage",
            sa.Enum(
                "queued",
                "starting",
                "completed",
                "failed",
                name="investigationstage",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_investigation_jobs_incident_id"),
        "investigation_jobs",
        ["incident_id"],
    )
    op.create_index(
        op.f("ix_investigation_jobs_project_id"),
        "investigation_jobs",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_investigation_jobs_stage"),
        "investigation_jobs",
        ["stage"],
    )
    op.create_index(
        op.f("ix_investigation_jobs_status"),
        "investigation_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_investigation_jobs_status"), table_name="investigation_jobs")
    op.drop_index(op.f("ix_investigation_jobs_stage"), table_name="investigation_jobs")
    op.drop_index(
        op.f("ix_investigation_jobs_project_id"),
        table_name="investigation_jobs",
    )
    op.drop_index(
        op.f("ix_investigation_jobs_incident_id"),
        table_name="investigation_jobs",
    )
    op.drop_table("investigation_jobs")
