"""OpenSearch connector errors."""

from __future__ import annotations

from app.connectors.search.errors import (
    SearchIndexError,
    SearchIndexNotConnectedError,
    SearchIndexQueryError,
    SearchIndexTimeoutError,
)


class OpenSearchError(SearchIndexError):
    """Base error for OpenSearch connector operations."""


class OpenSearchNotConnectedError(SearchIndexNotConnectedError):
    """Raised when a query runs without an active client session."""


class OpenSearchTimeoutError(SearchIndexTimeoutError):
    """Raised when an OpenSearch HTTP request exceeds the configured timeout."""


class OpenSearchQueryError(SearchIndexQueryError):
    """Raised when OpenSearch returns an error response for a query."""
