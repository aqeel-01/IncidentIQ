"""Verify the Alembic migrations build the expected schema and reverse cleanly."""

from __future__ import annotations

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import get_settings

CORE_TABLES = {
    "organizations",
    "users",
    "projects",
    "services",
    "incidents",
    "events",
    "error_groups",
    "log_uploads",
}


def _table_names(sqlite_url: str) -> set[str]:
    engine = create_engine(sqlite_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_upgrade_and_downgrade(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migrations.db"
    sqlite_url = f"sqlite:///{db_file.as_posix()}"

    # env.py reads the URL from application settings.
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    get_settings.cache_clear()

    config = Config("alembic.ini")

    command.upgrade(config, "head")
    tables = _table_names(sqlite_url)
    assert CORE_TABLES <= tables
    assert "alembic_version" in tables

    command.downgrade(config, "base")
    remaining = _table_names(sqlite_url)
    assert not (CORE_TABLES & remaining)

    get_settings.cache_clear()
