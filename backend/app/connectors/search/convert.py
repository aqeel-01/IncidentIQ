"""Convert search hits into canonical log events."""

from __future__ import annotations

from typing import Any

from app.connectors.search.config import SearchIndexConnectorConfig
from app.domain.events import LogEvent
from app.domain.parsing.fields import parse_severity, parse_timestamp


def _field_value(source: dict[str, Any], field_name: str) -> Any | None:
    if field_name in source and source[field_name] not in (None, ""):
        return source[field_name]
    return None


def search_hit_to_log_event(
    hit: dict[str, Any],
    *,
    config: SearchIndexConnectorConfig,
    source_name: str,
    source_type: str,
) -> LogEvent | None:
    """Map a single search hit to a :class:`LogEvent`."""

    source = hit.get("_source")
    if not isinstance(source, dict):
        return None

    message_value = _field_value(source, config.message_field)
    if message_value is None:
        return None
    message = str(message_value).strip()
    if not message:
        return None

    timestamp = parse_timestamp(_field_value(source, config.timestamp_field))
    if timestamp is None:
        return None

    service_value = _field_value(source, config.service_field) or config.default_service
    environment_value = (
        _field_value(source, config.environment_field) or config.default_environment
    )
    severity = parse_severity(_field_value(source, config.severity_field))
    host_value = _field_value(source, config.host_field)
    request_id_value = _field_value(source, config.request_id_field)
    trace_id_value = _field_value(source, config.trace_id_field)

    return LogEvent(
        timestamp=timestamp,
        source=source_name,
        source_type=source_type,
        source_id=str(hit.get("_id")) if hit.get("_id") is not None else None,
        service=str(service_value) if service_value is not None else None,
        environment=str(environment_value) if environment_value is not None else None,
        message=message,
        severity=severity,
        host=str(host_value) if host_value is not None else None,
        request_id=str(request_id_value) if request_id_value is not None else None,
        trace_id=str(trace_id_value) if trace_id_value is not None else None,
        raw_data={
            "_index": hit.get("_index"),
            "_id": hit.get("_id"),
            "_source": source,
        },
    )


def search_response_to_log_events(
    response: dict[str, Any],
    *,
    config: SearchIndexConnectorConfig,
    source_name: str,
    source_type: str,
) -> list[LogEvent]:
    """Convert a search response into canonical log events."""

    hits = response.get("hits", {})
    if not isinstance(hits, dict):
        return []
    items = hits.get("hits", [])
    if not isinstance(items, list):
        return []

    events: list[LogEvent] = []
    for hit in items:
        if not isinstance(hit, dict):
            continue
        event = search_hit_to_log_event(
            hit,
            config=config,
            source_name=source_name,
            source_type=source_type,
        )
        if event is not None:
            events.append(event)
    return events
