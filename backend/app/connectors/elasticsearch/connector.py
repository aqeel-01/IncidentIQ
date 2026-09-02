"""Elasticsearch connector implementation."""

from __future__ import annotations

from app.connectors.elasticsearch.client import ElasticsearchHTTPClient
from app.connectors.elasticsearch.config import ElasticsearchConnectorConfig
from app.connectors.elasticsearch.errors import (
    ElasticsearchNotConnectedError,
    ElasticsearchQueryError,
    ElasticsearchTimeoutError,
)
from app.connectors.search.connector import SearchIndexConnector
from app.connectors.search.profile import ELASTICSEARCH_PROFILE


class ElasticsearchConnector(SearchIndexConnector):
    """Connector for Elasticsearch log indices via the HTTP API."""

    def __init__(
        self,
        config: ElasticsearchConnectorConfig,
        *,
        client: ElasticsearchHTTPClient | None = None,
    ) -> None:
        super().__init__(
            config,
            profile=ELASTICSEARCH_PROFILE,
            client=client,
            not_connected_error=ElasticsearchNotConnectedError,
            timeout_error=ElasticsearchTimeoutError,
            query_error=ElasticsearchQueryError,
        )

    @property
    def elasticsearch_config(self) -> ElasticsearchConnectorConfig:
        return self._search_config  # type: ignore[return-value]


def create_elasticsearch_connector(
    config: ElasticsearchConnectorConfig,
) -> ElasticsearchConnector:
    """Factory used by :class:`~app.connectors.registry.ConnectorRegistry`."""

    return ElasticsearchConnector(config)
