"""configured connectors table

Revision ID: 0012_configured_connectors
Revises: 0011_historical_rca_storage
Create Date: 2026-09-03

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_configured_connectors"
down_revision: str | None = "0011_historical_rca_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "configured_connectors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("connector_type", sa.String(length=40), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_success", sa.Boolean(), nullable=True),
        sa.Column("last_test_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_configured_connectors_project_name",
        ),
    )
    op.create_index(
        op.f("ix_configured_connectors_project_id"),
        "configured_connectors",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_configured_connectors_connector_type"),
        "configured_connectors",
        ["connector_type"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_configured_connectors_connector_type"),
        table_name="configured_connectors",
    )
    op.drop_index(
        op.f("ix_configured_connectors_project_id"),
        table_name="configured_connectors",
    )
    op.drop_table("configured_connectors")
