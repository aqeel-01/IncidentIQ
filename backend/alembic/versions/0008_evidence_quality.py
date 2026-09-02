"""evidence quality persistence

Revision ID: 0008_evidence_quality
Revises: 0007_evidence_graph
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_evidence_quality"
down_revision: str | None = "0007_evidence_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_groups",
        sa.Column("quality_data", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence_groups", "quality_data")
