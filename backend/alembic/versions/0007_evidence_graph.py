"""evidence graph persistence

Revision ID: 0007_evidence_graph
Revises: 0006_evidence
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_evidence_graph"
down_revision: str | None = "0006_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_groups",
        sa.Column("graph_data", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence_groups", "graph_data")
