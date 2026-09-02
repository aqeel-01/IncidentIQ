"""SQL dialect helpers for the database log connector."""

from __future__ import annotations

import enum
import re


class SqlDialect(enum.StrEnum):
    """Supported SQL backends for log queries."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


_IDENTIFIER_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_sql_identifier(name: str, *, label: str = "identifier") -> str:
    """Reject identifiers that could enable SQL injection."""

    if not name or not name.strip():
        msg = f"{label} must not be empty"
        raise ValueError(msg)
    if not _IDENTIFIER_PART.match(name):
        msg = f"{label} contains invalid characters: {name!r}"
        raise ValueError(msg)
    return name


def validate_qualified_table_name(table: str) -> str:
    """Validate a table name, optionally schema-qualified."""

    parts = table.split(".")
    if not parts or len(parts) > 2:
        msg = f"table name must be unqualified or schema-qualified: {table!r}"
        raise ValueError(msg)
    for part in parts:
        validate_sql_identifier(part, label="table name")
    return table


def quote_identifier(name: str, dialect: SqlDialect) -> str:
    """Return a safely quoted SQL identifier for the given dialect."""

    validate_sql_identifier(name)
    if dialect is SqlDialect.POSTGRESQL:
        return f'"{name}"'
    return f"`{name}`"


def quote_qualified_table(table: str, dialect: SqlDialect) -> str:
    """Quote a table reference that may include a schema prefix."""

    validate_qualified_table_name(table)
    parts = table.split(".")
    return ".".join(quote_identifier(part, dialect) for part in parts)


def normalize_connection_url(url: str, dialect: SqlDialect) -> str:
    """Normalize a DSN to an async SQLAlchemy driver URL."""

    if dialect is SqlDialect.POSTGRESQL:
        for prefix in ("postgresql+asyncpg://",):
            if url.startswith(prefix):
                return url
        for sync_prefix, async_prefix in (
            ("postgresql://", "postgresql+asyncpg://"),
            ("postgresql+psycopg://", "postgresql+asyncpg://"),
            ("postgresql+psycopg2://", "postgresql+asyncpg://"),
        ):
            if url.startswith(sync_prefix):
                return async_prefix + url[len(sync_prefix) :]
        msg = "postgresql connection_url must use a postgresql:// scheme"
        raise ValueError(msg)

    for prefix in ("mysql+asyncmy://",):
        if url.startswith(prefix):
            return url
    for sync_prefix, async_prefix in (
        ("mysql://", "mysql+asyncmy://"),
        ("mysql+pymysql://", "mysql+asyncmy://"),
        ("mysql+mysqldb://", "mysql+asyncmy://"),
    ):
        if url.startswith(sync_prefix):
            return async_prefix + url[len(sync_prefix) :]
    msg = "mysql connection_url must use a mysql:// scheme"
    raise ValueError(msg)
