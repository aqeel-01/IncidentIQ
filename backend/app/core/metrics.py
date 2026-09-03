"""Prometheus metrics for IncidentIQ observability.

Metrics are always recorded in-process. Scraping ``GET /metrics`` does not
require an external Prometheus server, and application startup/readiness never
depends on Prometheus being available.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlparse

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

REGISTRY = CollectorRegistry(auto_describe=True)

_HTTP_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)
_JOB_LATENCY_BUCKETS = (0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)
_AI_LATENCY_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)

HTTP_REQUESTS_TOTAL = Counter(
    "incidentiq_http_requests_total",
    "Total HTTP requests handled by the API.",
    labelnames=("method", "status"),
    registry=REGISTRY,
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "incidentiq_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "status"),
    buckets=_HTTP_LATENCY_BUCKETS,
    registry=REGISTRY,
)
INVESTIGATION_JOBS_TOTAL = Counter(
    "incidentiq_investigation_jobs_total",
    "Investigation jobs completed or failed.",
    labelnames=("status",),
    registry=REGISTRY,
)
INVESTIGATION_DURATION_SECONDS = Histogram(
    "incidentiq_investigation_duration_seconds",
    "Investigation job duration from start to completion.",
    labelnames=("status",),
    buckets=_JOB_LATENCY_BUCKETS,
    registry=REGISTRY,
)
AI_REQUESTS_TOTAL = Counter(
    "incidentiq_ai_requests_total",
    "AI provider generate/structured_generate calls.",
    labelnames=("provider", "outcome"),
    registry=REGISTRY,
)
AI_REQUEST_DURATION_SECONDS = Histogram(
    "incidentiq_ai_request_duration_seconds",
    "AI provider request latency in seconds.",
    labelnames=("provider",),
    buckets=_AI_LATENCY_BUCKETS,
    registry=REGISTRY,
)
CELERY_QUEUE_LENGTH = Gauge(
    "incidentiq_celery_queue_length",
    "Approximate Celery broker queue depth.",
    labelnames=("queue",),
    registry=REGISTRY,
)
CONNECTOR_TEST_FAILURES_TOTAL = Counter(
    "incidentiq_connector_test_failures_total",
    "Failed connector connection tests.",
    labelnames=("connector_type",),
    registry=REGISTRY,
)
RCA_FAILURES_TOTAL = Counter(
    "incidentiq_rca_failures_total",
    "RCA stage failures during investigation.",
    labelnames=("stage",),
    registry=REGISTRY,
)

_EXCLUDED_METRIC_PATH_PREFIXES = (
    "/metrics",
    "/health",
)


def should_track_http_path(path: str) -> bool:
    """Return False for endpoints excluded from HTTP latency metrics."""

    return not any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in _EXCLUDED_METRIC_PATH_PREFIXES
    )


def observe_http_request(
    *, method: str, status_code: int, duration_seconds: float
) -> None:
    status = str(status_code)
    method_label = method.upper()
    HTTP_REQUESTS_TOTAL.labels(method=method_label, status=status).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method_label,
        status=status,
    ).observe(max(duration_seconds, 0.0))


def observe_investigation_finished(
    *,
    status: str,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> None:
    status_label = status.lower()
    INVESTIGATION_JOBS_TOTAL.labels(status=status_label).inc()
    if started_at is not None and completed_at is not None:
        duration = (completed_at - started_at).total_seconds()
        INVESTIGATION_DURATION_SECONDS.labels(status=status_label).observe(
            max(duration, 0.0)
        )


@asynccontextmanager
async def track_ai_request(provider: str) -> AsyncIterator[None]:
    """Time an AI provider call and record success/error outcome."""

    start = time.perf_counter()
    outcome = "success"
    try:
        yield
    except Exception:
        outcome = "error"
        raise
    finally:
        AI_REQUEST_DURATION_SECONDS.labels(provider=provider).observe(
            max(time.perf_counter() - start, 0.0)
        )
        AI_REQUESTS_TOTAL.labels(provider=provider, outcome=outcome).inc()


def observe_connector_test_failure(connector_type: str) -> None:
    CONNECTOR_TEST_FAILURES_TOTAL.labels(connector_type=connector_type).inc()


def observe_rca_failure(stage: str) -> None:
    RCA_FAILURES_TOTAL.labels(stage=stage).inc()


def update_celery_queue_length(*, broker_url: str, queue: str) -> None:
    """Best-effort Redis ``LLEN`` for Celery queue depth. Never raises."""

    try:
        length = _redis_queue_length(broker_url, queue)
    except Exception:  # noqa: BLE001 - metrics must not break scrapes
        logger.debug("celery queue length unavailable", exc_info=True)
        return
    if length is None:
        return
    CELERY_QUEUE_LENGTH.labels(queue=queue).set(length)


def _redis_queue_length(broker_url: str, queue: str) -> int | None:
    parsed = urlparse(broker_url)
    if parsed.scheme not in {"redis", "rediss"}:
        return None

    try:
        import redis
    except ImportError:
        return None

    client = redis.Redis.from_url(broker_url, socket_connect_timeout=0.5)
    try:
        value = client.llen(queue)
    finally:
        client.close()
    return int(value)


def render_metrics(
    *,
    broker_url: str | None = None,
    queue: str | None = None,
) -> tuple[bytes, str]:
    """Return Prometheus metrics payload and content type."""

    if broker_url and queue:
        update_celery_queue_length(broker_url=broker_url, queue=queue)
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
