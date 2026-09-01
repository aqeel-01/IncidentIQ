"""Declarative base for all ORM models.

Models (added in later steps) must inherit from :class:`Base` and be imported
somewhere that Alembic's ``env.py`` loads, so that ``Base.metadata`` reflects
the full schema for autogeneration. No concrete models exist yet.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common declarative base carrying shared metadata for all models."""
