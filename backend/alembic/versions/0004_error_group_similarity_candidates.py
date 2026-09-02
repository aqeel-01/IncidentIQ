"""error group similarity investigation candidates

Revision ID: 0004_error_group_similarity_candidates
Revises: 0003_log_uploads
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_error_group_similarity_candidates"
down_revision: str | None = "0003_log_uploads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "error_group_similarity_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_error_group_id", sa.Integer(), nullable=False),
        sa.Column("candidate_error_group_id", sa.Integer(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["source_error_group_id"], ["error_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_error_group_id"], ["error_groups.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_error_group_id",
            "candidate_error_group_id",
            name="uq_error_group_similarity_candidate_pair",
        ),
    )
    op.create_index(
        "ix_error_group_similarity_candidates_project",
        "error_group_similarity_candidates",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_error_group_similarity_candidates_source_error_group_id"),
        "error_group_similarity_candidates",
        ["source_error_group_id"],
    )
    op.create_index(
        op.f("ix_error_group_similarity_candidates_candidate_error_group_id"),
        "error_group_similarity_candidates",
        ["candidate_error_group_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_error_group_similarity_candidates_candidate_error_group_id"),
        table_name="error_group_similarity_candidates",
    )
    op.drop_index(
        op.f("ix_error_group_similarity_candidates_source_error_group_id"),
        table_name="error_group_similarity_candidates",
    )
    op.drop_index(
        "ix_error_group_similarity_candidates_project",
        table_name="error_group_similarity_candidates",
    )
    op.drop_table("error_group_similarity_candidates")
