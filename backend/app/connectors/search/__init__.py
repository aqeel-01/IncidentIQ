"""Shared search-index connector building blocks."""

from app.connectors.search.config import SearchIndexConnectorConfig
from app.connectors.search.connector import SearchIndexConnector
from app.connectors.search.convert import (
    search_hit_to_log_event,
    search_response_to_log_events,
)
from app.connectors.search.errors import (
    SearchIndexError,
    SearchIndexNotConnectedError,
    SearchIndexQueryError,
    SearchIndexTimeoutError,
)
from app.connectors.search.profile import (
    ELASTICSEARCH_PROFILE,
    OPENSEARCH_PROFILE,
    SearchConnectorProfile,
)
from app.connectors.search.query import build_log_search_body, search_path_for_index
from app.connectors.search.types import LogQueryFilters

__all__ = [
    "ELASTICSEARCH_PROFILE",
    "LogQueryFilters",
    "OPENSEARCH_PROFILE",
    "SearchConnectorProfile",
    "SearchIndexConnector",
    "SearchIndexConnectorConfig",
    "SearchIndexError",
    "SearchIndexNotConnectedError",
    "SearchIndexQueryError",
    "SearchIndexTimeoutError",
    "build_log_search_body",
    "search_hit_to_log_event",
    "search_path_for_index",
    "search_response_to_log_events",
]
