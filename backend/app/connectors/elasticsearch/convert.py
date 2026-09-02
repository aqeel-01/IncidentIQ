"""Convert Elasticsearch hits into canonical log events."""

from __future__ import annotations

from typing import Any

from app.connectors.elasticsearch.config import ElasticsearchConnectorConfig
from app.connectors.search.convert import (
    search_hit_to_log_event,
    search_response_to_log_events,
)
from app.domain.events import LogEvent


def elasticsearch_hit_to_log_event(
    hit: dict[str, Any],
    *,
    config: ElasticsearchConnectorConfig,
    source_name: str,
) -> LogEvent | None:
    """Map a single Elasticsearch search hit to a :class:`LogEvent`."""

    return search_hit_to_log_event(
        hit,
        config=config,
        source_name=source_name,
        source_type="elasticsearch",
    )


def elasticsearch_response_to_log_events(
    response: dict[str, Any],
    *,
    config: ElasticsearchConnectorConfig,
    source_name: str,
) -> list[LogEvent]:
    """Convert an Elasticsearch search response into canonical log events."""

    return search_response_to_log_events(
        response,
        config=config,
        source_name=source_name,
        source_type="elasticsearch",
    )
