"""HTTP client for Elasticsearch API access."""

from __future__ import annotations

from app.connectors.elasticsearch.config import ElasticsearchConnectorConfig
from app.connectors.elasticsearch.errors import ElasticsearchTimeoutError
from app.connectors.search.client import HttpxSearchClient, SearchHTTPClient

ElasticsearchHTTPClient = SearchHTTPClient


class HttpxElasticsearchClient(HttpxSearchClient):
    """Async Elasticsearch HTTP client backed by ``httpx``."""

    def __init__(self, config: ElasticsearchConnectorConfig) -> None:
        super().__init__(
            config,
            system_name="elasticsearch",
            timeout_error=ElasticsearchTimeoutError,
        )
