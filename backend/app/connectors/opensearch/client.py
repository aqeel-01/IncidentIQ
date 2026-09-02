"""HTTP client for OpenSearch API access."""

from __future__ import annotations

from app.connectors.opensearch.config import OpenSearchConnectorConfig
from app.connectors.opensearch.errors import OpenSearchTimeoutError
from app.connectors.search.client import HttpxSearchClient, SearchHTTPClient

OpenSearchHTTPClient = SearchHTTPClient


class HttpxOpenSearchClient(HttpxSearchClient):
    """Async OpenSearch HTTP client backed by ``httpx``."""

    def __init__(self, config: OpenSearchConnectorConfig) -> None:
        super().__init__(
            config,
            system_name="opensearch",
            timeout_error=OpenSearchTimeoutError,
        )
