"""Elasticsearch log connector."""

from app.connectors.elasticsearch.config import ElasticsearchConnectorConfig
from app.connectors.elasticsearch.connector import (
    ElasticsearchConnector,
    create_elasticsearch_connector,
)
from app.connectors.elasticsearch.convert import (
    elasticsearch_hit_to_log_event,
    elasticsearch_response_to_log_events,
)
from app.connectors.elasticsearch.errors import (
    ElasticsearchError,
    ElasticsearchNotConnectedError,
    ElasticsearchQueryError,
    ElasticsearchTimeoutError,
)
from app.connectors.elasticsearch.query import build_log_search_body
from app.connectors.elasticsearch.types import LogQueryFilters

__all__ = [
    "ElasticsearchConnector",
    "ElasticsearchConnectorConfig",
    "ElasticsearchError",
    "ElasticsearchNotConnectedError",
    "ElasticsearchQueryError",
    "ElasticsearchTimeoutError",
    "LogQueryFilters",
    "build_log_search_body",
    "create_elasticsearch_connector",
    "elasticsearch_hit_to_log_event",
    "elasticsearch_response_to_log_events",
]
