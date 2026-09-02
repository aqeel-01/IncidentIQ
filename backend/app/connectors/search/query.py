"""Search request builders shared by OpenSearch and Elasticsearch."""

from __future__ import annotations

from datetime import UTC
from typing import Any

from app.connectors.search.config import SearchIndexConnectorConfig
from app.connectors.search.types import LogQueryFilters
from app.db.models.enums import Severity

_SEVERITY_QUERY_VALUES: dict[Severity, tuple[str, ...]] = {
    Severity.INFO: ("info", "information", "debug", "trace"),
    Severity.LOW: ("low", "notice"),
    Severity.MEDIUM: ("medium", "warn", "warning"),
    Severity.HIGH: ("high", "error", "err"),
    Severity.CRITICAL: ("critical", "crit", "fatal", "emergency"),
}


def _severity_terms(severity: Severity) -> list[str]:
    return list(_SEVERITY_QUERY_VALUES.get(severity, (severity.value.lower(),)))


def build_log_search_body(
    filters: LogQueryFilters,
    config: SearchIndexConnectorConfig,
) -> dict[str, Any]:
    """Build a search DSL query for a time-bounded log search."""

    start = filters.start.astimezone(UTC).isoformat()
    end = filters.end.astimezone(UTC).isoformat()
    query_filters: list[dict[str, Any]] = [
        {
            "range": {
                config.timestamp_field: {
                    "gte": start,
                    "lte": end,
                }
            }
        }
    ]

    if filters.service:
        query_filters.append({"term": {config.service_field: filters.service}})
    if filters.environment:
        query_filters.append({"term": {config.environment_field: filters.environment}})
    if filters.severity is not None:
        terms = _severity_terms(filters.severity)
        if len(terms) == 1:
            query_filters.append({"term": {config.severity_field: terms[0]}})
        else:
            query_filters.append({"terms": {config.severity_field: terms}})

    return {
        "size": filters.size,
        "sort": [{config.timestamp_field: {"order": "asc"}}],
        "query": {"bool": {"filter": query_filters}},
    }


def search_path_for_index(index: str) -> str:
    return f"/{index}/_search"
