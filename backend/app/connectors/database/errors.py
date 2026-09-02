"""Database connector errors."""

from __future__ import annotations

from app.connectors.errors import (
    ConnectorConnectionError,
    ConnectorError,
    ConnectorNotConnectedError,
)


class DatabaseError(ConnectorError):
    """Base error for database connector operations."""


class DatabaseNotConnectedError(ConnectorNotConnectedError):
    """Raised when a query runs without an active database session."""


class DatabaseConnectionError(DatabaseError, ConnectorConnectionError):
    """Raised when the database connection fails."""


class DatabaseQueryError(DatabaseError):
    """Raised when a log query fails."""


class DatabaseReadOnlyError(DatabaseError):
    """Raised when SQL violates read-only restrictions."""


class DatabaseMappingError(DatabaseError):
    """Raised when row data cannot be mapped to a log event."""
