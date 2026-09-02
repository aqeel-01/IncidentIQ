"""Convert OpenSearch hits into canonical log events."""

from __future__ import annotations

from typing import Any

from app.connectors.opensearch.config import OpenSearchConnectorConfig
from app.connectors.search.convert import (
    search_hit_to_log_event,
    search_response_to_log_events,
)
from app.domain.events import LogEvent


def opensearch_hit_to_log_event(
    hit: dict[str, Any],
    *,
    config: OpenSearchConnectorConfig,
    source_name: str,
) -> LogEvent | None:
    """Map a single OpenSearch search hit to a :class:`LogEvent`."""

    return search_hit_to_log_event(
        hit,
        config=config,
        source_name=source_name,
        source_type="opensearch",
    )


def opensearch_response_to_log_events(
    response: dict[str, Any],
    *,
    config: OpenSearchConnectorConfig,
    source_name: str,
) -> list[LogEvent]:
    """Convert an OpenSearch search response into canonical log events."""

    return search_response_to_log_events(
        response,
        config=config,
        source_name=source_name,
        source_type="opensearch",
    )
