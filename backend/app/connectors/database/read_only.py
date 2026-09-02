"""Read-only SQL enforcement for the database log connector."""

from __future__ import annotations

import re

from app.connectors.database.errors import DatabaseReadOnlyError

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|"
    r"GRANT|REVOKE|EXEC|EXECUTE|CALL|ATTACH|DETACH|PRAGMA|VACUUM|"
    r"INTO|SET|COPY|LOAD|IMPORT|EXPORT|RENAME|COMMENT|LOCK|UNLOCK"
    r")\b",
    re.IGNORECASE,
)

_SQL_COMMENTS = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)


def _strip_sql_comments(sql: str) -> str:
    return _SQL_COMMENTS.sub(" ", sql)


def validate_read_only_sql(sql: str) -> None:
    """Ensure ``sql`` is a single read-only ``SELECT`` statement."""

    cleaned = _strip_sql_comments(sql).strip().rstrip(";")
    if not cleaned:
        msg = "SQL statement must not be empty"
        raise DatabaseReadOnlyError(msg)

    statements = [part.strip() for part in cleaned.split(";") if part.strip()]
    if len(statements) != 1:
        msg = "only a single SQL statement is permitted"
        raise DatabaseReadOnlyError(msg)

    statement = statements[0]
    if not re.match(r"^SELECT\b", statement, re.IGNORECASE):
        msg = "only SELECT statements are permitted"
        raise DatabaseReadOnlyError(msg)

    if _FORBIDDEN_KEYWORDS.search(statement):
        msg = "destructive or mutating SQL keywords are not permitted"
        raise DatabaseReadOnlyError(msg)
