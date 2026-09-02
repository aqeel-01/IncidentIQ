"""incident fingerprint for deduplication

Revision ID: 0005_incident_fingerprint
Revises: 0004_error_group_similarity_candidates
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_incident_fingerprint"
down_revision: str | None = "0004_error_group_similarity_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column(
            "fingerprint",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(
        "ix_incidents_project_fingerprint",
        "incidents",
        ["project_id", "fingerprint"],
    )
    op.create_index(
        op.f("ix_incidents_fingerprint"),
        "incidents",
        ["fingerprint"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_incidents_fingerprint"), table_name="incidents")
    op.drop_index("ix_incidents_project_fingerprint", table_name="incidents")
    op.drop_column("incidents", "fingerprint")
