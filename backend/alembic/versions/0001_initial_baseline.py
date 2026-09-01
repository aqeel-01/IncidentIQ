"""initial baseline

Establishes the migration baseline. No application tables are created yet;
models and their migrations are added in later steps.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-09-01

"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_initial_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
