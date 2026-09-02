"""OpenSearch log connector."""

from app.connectors.opensearch.config import OpenSearchConnectorConfig
from app.connectors.opensearch.connector import (
    OpenSearchConnector,
    create_opensearch_connector,
)
from app.connectors.opensearch.convert import (
    opensearch_hit_to_log_event,
    opensearch_response_to_log_events,
)
from app.connectors.opensearch.errors import (
    OpenSearchError,
    OpenSearchNotConnectedError,
    OpenSearchQueryError,
    OpenSearchTimeoutError,
)
from app.connectors.opensearch.query import build_log_search_body
from app.connectors.opensearch.types import LogQueryFilters

__all__ = [
    "LogQueryFilters",
    "OpenSearchConnector",
    "OpenSearchConnectorConfig",
    "OpenSearchError",
    "OpenSearchNotConnectedError",
    "OpenSearchQueryError",
    "OpenSearchTimeoutError",
    "build_log_search_body",
    "create_opensearch_connector",
    "opensearch_hit_to_log_event",
    "opensearch_response_to_log_events",
]
