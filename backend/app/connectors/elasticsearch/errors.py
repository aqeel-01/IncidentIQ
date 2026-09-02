"""Elasticsearch connector errors."""

from __future__ import annotations

from app.connectors.search.errors import (
    SearchIndexError,
    SearchIndexNotConnectedError,
    SearchIndexQueryError,
    SearchIndexTimeoutError,
)


class ElasticsearchError(SearchIndexError):
    """Base error for Elasticsearch connector operations."""


class ElasticsearchNotConnectedError(SearchIndexNotConnectedError):
    """Raised when a query runs without an active client session."""


class ElasticsearchTimeoutError(SearchIndexTimeoutError):
    """Raised when an Elasticsearch HTTP request exceeds the configured timeout."""


class ElasticsearchQueryError(SearchIndexQueryError):
    """Raised when Elasticsearch returns an error response for a query."""
