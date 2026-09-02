"""Shared errors for Elasticsearch-compatible search connectors."""

from __future__ import annotations

from app.connectors.errors import (
    ConnectorConnectionError,
    ConnectorError,
    ConnectorNotConnectedError,
)


class SearchIndexError(ConnectorError):
    """Base error for search index connector operations."""


class SearchIndexNotConnectedError(ConnectorNotConnectedError):
    """Raised when a query runs without an active client session."""


class SearchIndexTimeoutError(SearchIndexError, ConnectorConnectionError):
    """Raised when a search HTTP request exceeds the configured timeout."""


class SearchIndexQueryError(SearchIndexError):
    """Raised when a search backend returns an error response for a query."""
