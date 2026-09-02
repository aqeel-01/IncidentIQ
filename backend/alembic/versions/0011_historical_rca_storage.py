"""historical RCA storage metadata

Revision ID: 0011_historical_rca_storage
Revises: 0010_investigation_pipeline
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_historical_rca_storage"
down_revision: str | None = "0010_investigation_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rca_results") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ai_provider",
                sa.String(length=40),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "ai_model",
                sa.String(length=120),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_quality",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    with op.batch_alter_table("investigation_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("rca_result_id", sa.Integer(), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_investigation_jobs_rca_result_id",
            "rca_results",
            ["rca_result_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_investigation_jobs_rca_result_id"),
            ["rca_result_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("investigation_jobs") as batch_op:
        batch_op.drop_index(batch_op.f("ix_investigation_jobs_rca_result_id"))
        batch_op.drop_constraint(
            "fk_investigation_jobs_rca_result_id",
            type_="foreignkey",
        )
        batch_op.drop_column("rca_result_id")

    with op.batch_alter_table("rca_results") as batch_op:
        batch_op.drop_column("evidence_quality")
        batch_op.drop_column("ai_model")
        batch_op.drop_column("ai_provider")
