"""Read-only SQL database log connector."""

from app.connectors.database.config import DatabaseConnectorConfig
from app.connectors.database.connector import (
    DatabaseConnector,
    create_database_connector,
)
from app.connectors.database.convert import sql_row_to_log_event, sql_rows_to_log_events
from app.connectors.database.dialect import SqlDialect
from app.connectors.database.errors import (
    DatabaseConnectionError,
    DatabaseError,
    DatabaseMappingError,
    DatabaseNotConnectedError,
    DatabaseQueryError,
    DatabaseReadOnlyError,
)
from app.connectors.database.query import BuiltLogQuery, build_log_select_query
from app.connectors.database.read_only import validate_read_only_sql
from app.connectors.database.types import LogQueryFilters

__all__ = [
    "BuiltLogQuery",
    "DatabaseConnectionError",
    "DatabaseConnector",
    "DatabaseConnectorConfig",
    "DatabaseError",
    "DatabaseMappingError",
    "DatabaseNotConnectedError",
    "DatabaseQueryError",
    "DatabaseReadOnlyError",
    "LogQueryFilters",
    "SqlDialect",
    "build_log_select_query",
    "create_database_connector",
    "sql_row_to_log_event",
    "sql_rows_to_log_events",
    "validate_read_only_sql",
]
