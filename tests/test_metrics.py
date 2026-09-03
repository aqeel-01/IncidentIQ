"""Observability / Prometheus metrics tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.metrics import (
    observe_connector_test_failure,
    observe_http_request,
    observe_investigation_finished,
    observe_rca_failure,
    render_metrics,
    track_ai_request,
    update_celery_queue_length,
)
from app.main import create_app


@pytest.fixture
def metrics_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_metrics_endpoint_is_public_and_prometheus_text(
    metrics_client: TestClient,
) -> None:
    observe_http_request(method="GET", status_code=200, duration_seconds=0.01)
    response = metrics_client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "incidentiq_http_requests_total" in body
    assert "incidentiq_http_request_duration_seconds" in body
    assert "incidentiq_investigation_duration_seconds" in body
    assert "incidentiq_ai_request_duration_seconds" in body
    assert "incidentiq_celery_queue_length" in body
    assert "incidentiq_connector_test_failures_total" in body
    assert "incidentiq_rca_failures_total" in body


def test_health_still_works_without_external_prometheus(
    metrics_client: TestClient,
) -> None:
    response = metrics_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_http_metrics_recorded_for_api_requests(
    metrics_client: TestClient,
) -> None:
    metrics_client.get("/health")
    body = metrics_client.get("/metrics").text
    assert 'incidentiq_http_requests_total{method="GET",status="200"}' in body


def _counter_value(body: str, metric_line_prefix: str) -> float:
    for line in body.splitlines():
        if line.startswith(metric_line_prefix + " "):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def test_metrics_path_is_excluded_from_http_latency_counting(
    metrics_client: TestClient,
) -> None:
    prefix = 'incidentiq_http_requests_total{method="GET",status="200"}'
    before = _counter_value(metrics_client.get("/metrics").text, prefix)
    metrics_client.get("/metrics")
    after = _counter_value(metrics_client.get("/metrics").text, prefix)
    # /metrics itself must not increment the HTTP counter.
    assert after == before


def test_investigation_and_rca_metrics_helpers() -> None:
    started = datetime.now(UTC) - timedelta(seconds=3)
    completed = datetime.now(UTC)
    observe_investigation_finished(
        status="completed",
        started_at=started,
        completed_at=completed,
    )
    observe_investigation_finished(
        status="failed",
        started_at=started,
        completed_at=completed,
    )
    observe_rca_failure("run_rca")
    observe_connector_test_failure("prometheus")

    payload, _ = render_metrics()
    text = payload.decode("utf-8")
    assert 'incidentiq_investigation_jobs_total{status="completed"}' in text
    assert 'incidentiq_investigation_jobs_total{status="failed"}' in text
    assert "incidentiq_investigation_duration_seconds_bucket" in text
    assert 'incidentiq_rca_failures_total{stage="run_rca"}' in text
    assert (
        'incidentiq_connector_test_failures_total{connector_type="prometheus"}' in text
    )


@pytest.mark.asyncio
async def test_ai_latency_metric_tracks_success_and_error() -> None:
    async with track_ai_request("ollama"):
        pass

    with pytest.raises(RuntimeError, match="boom"):
        async with track_ai_request("groq"):
            raise RuntimeError("boom")

    payload, _ = render_metrics()
    text = payload.decode("utf-8")
    assert 'incidentiq_ai_requests_total{outcome="success",provider="ollama"}' in text
    assert 'incidentiq_ai_requests_total{outcome="error",provider="groq"}' in text
    assert 'incidentiq_ai_request_duration_seconds_count{provider="ollama"}' in text


def test_celery_queue_gauge_tolerates_unreachable_redis() -> None:
    # Must not raise when Redis is down — local startup remains usable.
    update_celery_queue_length(
        broker_url="redis://127.0.0.1:1/0",
        queue="investigation",
    )
    payload, _ = render_metrics(
        broker_url="redis://127.0.0.1:1/0",
        queue="investigation",
    )
    assert b"incidentiq_celery_queue_length" in payload
