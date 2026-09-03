"""project memberships and roles

Revision ID: 0013_project_memberships
Revises: 0012_configured_connectors
Create Date: 2026-09-03

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_project_memberships"
down_revision: str | None = "0012_configured_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "project_id",
            name="uq_project_memberships_user_project",
        ),
    )
    op.create_index(
        op.f("ix_project_memberships_project_id"),
        "project_memberships",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_memberships_user_id"),
        "project_memberships",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_project_memberships_user_id"),
        table_name="project_memberships",
    )
    op.drop_index(
        op.f("ix_project_memberships_project_id"),
        table_name="project_memberships",
    )
    op.drop_table("project_memberships")
