"""OpenSearch connector implementation."""

from __future__ import annotations

from app.connectors.opensearch.client import OpenSearchHTTPClient
from app.connectors.opensearch.config import OpenSearchConnectorConfig
from app.connectors.opensearch.errors import (
    OpenSearchNotConnectedError,
    OpenSearchQueryError,
    OpenSearchTimeoutError,
)
from app.connectors.search.connector import SearchIndexConnector
from app.connectors.search.profile import OPENSEARCH_PROFILE


class OpenSearchConnector(SearchIndexConnector):
    """Connector for OpenSearch log indices via the HTTP API."""

    def __init__(
        self,
        config: OpenSearchConnectorConfig,
        *,
        client: OpenSearchHTTPClient | None = None,
    ) -> None:
        super().__init__(
            config,
            profile=OPENSEARCH_PROFILE,
            client=client,
            not_connected_error=OpenSearchNotConnectedError,
            timeout_error=OpenSearchTimeoutError,
            query_error=OpenSearchQueryError,
        )

    @property
    def opensearch_config(self) -> OpenSearchConnectorConfig:
        return self._search_config  # type: ignore[return-value]


def create_opensearch_connector(
    config: OpenSearchConnectorConfig,
) -> OpenSearchConnector:
    """Factory used by :class:`~app.connectors.registry.ConnectorRegistry`."""

    return OpenSearchConnector(config)
