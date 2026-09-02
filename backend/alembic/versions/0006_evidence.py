"""evidence package persistence

Revision ID: 0006_evidence
Revises: 0005_incident_fingerprint
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_evidence"
down_revision: str | None = "0005_incident_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
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
        "ix_evidence_groups_incident_built_at",
        "evidence_groups",
        ["incident_id", "built_at"],
    )
    op.create_index("ix_evidence_groups_project", "evidence_groups", ["project_id"])
    op.create_index(
        op.f("ix_evidence_groups_incident_id"),
        "evidence_groups",
        ["incident_id"],
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_group_id", sa.Integer(), nullable=False),
        sa.Column("evidence_key", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("error_group_id", sa.Integer(), nullable=True),
        sa.Column("timeline_entry_id", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("stance", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["evidence_group_id"], ["evidence_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["error_group_id"], ["error_groups.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_evidence_group_id"),
        "evidence",
        ["evidence_group_id"],
    )
    op.create_index(op.f("ix_evidence_source"), "evidence", ["source"])
    op.create_index(op.f("ix_evidence_event_id"), "evidence", ["event_id"])
    op.create_index(
        op.f("ix_evidence_error_group_id"),
        "evidence",
        ["error_group_id"],
    )
    op.create_index(op.f("ix_evidence_stance"), "evidence", ["stance"])

    op.create_table(
        "evidence_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_group_id", sa.Integer(), nullable=False),
        sa.Column("relation_key", sa.String(length=128), nullable=False),
        sa.Column("source_evidence_id", sa.Integer(), nullable=False),
        sa.Column("target_evidence_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["evidence_group_id"], ["evidence_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_evidence_id"], ["evidence.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_evidence_id"], ["evidence.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_group_id",
            "relation_key",
            name="uq_evidence_relations_group_key",
        ),
    )
    op.create_index(
        op.f("ix_evidence_relations_evidence_group_id"),
        "evidence_relations",
        ["evidence_group_id"],
    )
    op.create_index(
        op.f("ix_evidence_relations_source_evidence_id"),
        "evidence_relations",
        ["source_evidence_id"],
    )
    op.create_index(
        op.f("ix_evidence_relations_target_evidence_id"),
        "evidence_relations",
        ["target_evidence_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_evidence_relations_target_evidence_id"),
        table_name="evidence_relations",
    )
    op.drop_index(
        op.f("ix_evidence_relations_source_evidence_id"),
        table_name="evidence_relations",
    )
    op.drop_index(
        op.f("ix_evidence_relations_evidence_group_id"),
        table_name="evidence_relations",
    )
    op.drop_table("evidence_relations")
    op.drop_index(op.f("ix_evidence_stance"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_error_group_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_event_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_source"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_evidence_group_id"), table_name="evidence")
    op.drop_table("evidence")
    op.drop_index(op.f("ix_evidence_groups_incident_id"), table_name="evidence_groups")
    op.drop_index("ix_evidence_groups_project", table_name="evidence_groups")
    op.drop_index("ix_evidence_groups_incident_built_at", table_name="evidence_groups")
    op.drop_table("evidence_groups")
