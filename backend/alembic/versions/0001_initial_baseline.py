"""initial baseline

Establishes the migration baseline. No application tables are created yet;
models and their migrations are added in later steps.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-09-01

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic creates alembic_version.version_num as VARCHAR(32) by default.
    # Later revision ids in this project exceed that length. SQLite stores
    # VARCHAR as TEXT and does not enforce the limit.
    if op.get_bind().dialect.name == "sqlite":
        return
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"
    )


def downgrade() -> None:
    pass
