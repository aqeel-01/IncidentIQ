"""Elasticsearch connector configuration."""

from __future__ import annotations

from typing import Literal

from app.connectors.search.config import SearchIndexConnectorConfig
from app.connectors.types import ConnectorType


class ElasticsearchConnectorConfig(SearchIndexConnectorConfig):
    """Configuration for an Elasticsearch log connector."""

    connector_type: Literal[ConnectorType.ELASTICSEARCH] = ConnectorType.ELASTICSEARCH
