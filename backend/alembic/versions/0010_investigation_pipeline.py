"""investigation pipeline stages and RCA persistence

Revision ID: 0010_investigation_pipeline
Revises: 0009_investigation_jobs
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_investigation_pipeline"
down_revision: str | None = "0009_investigation_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("investigation_jobs") as batch_op:
        batch_op.alter_column(
            "stage",
            existing_type=sa.Enum(
                "queued",
                "starting",
                "completed",
                "failed",
                name="investigationstage",
                native_enum=False,
                length=20,
            ),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column(
                "stage_artifacts",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )

    op.create_table(
        "rca_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("investigation_job_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_group_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("engine_version", sa.String(length=20), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("result_data", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["evidence_group_id"], ["evidence_groups.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["investigation_job_id"],
            ["investigation_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rca_results_incident_id"), "rca_results", ["incident_id"])
    op.create_index(op.f("ix_rca_results_project_id"), "rca_results", ["project_id"])
    op.create_index(
        op.f("ix_rca_results_investigation_job_id"),
        "rca_results",
        ["investigation_job_id"],
    )
    op.create_index(
        op.f("ix_rca_results_evidence_group_id"),
        "rca_results",
        ["evidence_group_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rca_results_evidence_group_id"), table_name="rca_results")
    op.drop_index(
        op.f("ix_rca_results_investigation_job_id"),
        table_name="rca_results",
    )
    op.drop_index(op.f("ix_rca_results_project_id"), table_name="rca_results")
    op.drop_index(op.f("ix_rca_results_incident_id"), table_name="rca_results")
    op.drop_table("rca_results")

    with op.batch_alter_table("investigation_jobs") as batch_op:
        batch_op.drop_column("stage_artifacts")
        batch_op.alter_column(
            "stage",
            existing_type=sa.String(length=32),
            type_=sa.Enum(
                "queued",
                "starting",
                "completed",
                "failed",
                name="investigationstage",
                native_enum=False,
                length=20,
            ),
            existing_nullable=False,
        )
