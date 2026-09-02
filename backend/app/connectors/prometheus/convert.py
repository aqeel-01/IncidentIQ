"""Convert Prometheus query payloads into canonical metric events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.events import MetricEvent


def _timestamp_from_epoch(value: str | int | float) -> datetime:
    return datetime.fromtimestamp(float(value), tz=UTC)


def _metric_name(metric: dict[str, str]) -> str:
    return metric.get("__name__", "unknown_metric")


def _labels(metric: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in metric.items() if key != "__name__"}


def _sample_to_event(
    *,
    metric: dict[str, str],
    timestamp: datetime,
    value: float,
    source: str,
    source_type: str,
    service: str | None,
    environment: str | None,
    query: str,
    raw_sample: dict[str, Any],
) -> MetricEvent:
    return MetricEvent(
        timestamp=timestamp,
        source=source,
        source_type=source_type,
        service=service,
        environment=environment,
        metric_name=_metric_name(metric),
        value=value,
        labels=_labels(metric),
        raw_data={
            "query": query,
            "sample": raw_sample,
        },
    )


def prometheus_response_to_metric_events(
    *,
    response: dict[str, Any],
    query: str,
    source: str,
    source_type: str = "prometheus",
    service: str | None = None,
    environment: str | None = None,
) -> list[MetricEvent]:
    """Map a Prometheus instant/range query response to :class:`MetricEvent` rows."""

    if response.get("status") != "success":
        error_type = response.get("errorType", "unknown")
        error = response.get("error", "prometheus query failed")
        msg = f"{error_type}: {error}"
        raise ValueError(msg)

    data = response.get("data")
    if not isinstance(data, dict):
        return []

    result_type = data.get("resultType")
    result = data.get("result")
    events: list[MetricEvent] = []

    if result_type == "vector" and isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            metric = item.get("metric", {})
            value = item.get("value")
            if not isinstance(metric, dict) or not isinstance(value, list):
                continue
            if len(value) < 2:
                continue
            events.append(
                _sample_to_event(
                    metric={str(k): str(v) for k, v in metric.items()},
                    timestamp=_timestamp_from_epoch(value[0]),
                    value=float(value[1]),
                    source=source,
                    source_type=source_type,
                    service=service,
                    environment=environment,
                    query=query,
                    raw_sample=item,
                )
            )
        return events

    if result_type == "matrix" and isinstance(result, list):
        for series in result:
            if not isinstance(series, dict):
                continue
            metric = series.get("metric", {})
            values = series.get("values")
            if not isinstance(metric, dict) or not isinstance(values, list):
                continue
            metric_labels = {str(k): str(v) for k, v in metric.items()}
            for sample in values:
                if not isinstance(sample, list) or len(sample) < 2:
                    continue
                events.append(
                    _sample_to_event(
                        metric=metric_labels,
                        timestamp=_timestamp_from_epoch(sample[0]),
                        value=float(sample[1]),
                        source=source,
                        source_type=source_type,
                        service=service,
                        environment=environment,
                        query=query,
                        raw_sample={"metric": metric_labels, "value": sample},
                    )
                )
        return events

    if result_type == "scalar" and isinstance(result, list) and len(result) >= 2:
        events.append(
            _sample_to_event(
                metric={"__name__": query},
                timestamp=_timestamp_from_epoch(result[0]),
                value=float(result[1]),
                source=source,
                source_type=source_type,
                service=service,
                environment=environment,
                query=query,
                raw_sample={"value": result},
            )
        )

    return events
