"""OpenSearch connector configuration."""

from __future__ import annotations

from typing import Literal

from app.connectors.search.config import SearchIndexConnectorConfig
from app.connectors.types import ConnectorType


class OpenSearchConnectorConfig(SearchIndexConnectorConfig):
    """Configuration for an OpenSearch log connector."""

    connector_type: Literal[ConnectorType.OPENSEARCH] = ConnectorType.OPENSEARCH
