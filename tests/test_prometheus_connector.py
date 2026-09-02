"""Tests for the Prometheus connector."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.connectors import ConnectorRegistry, ConnectorState, ConnectorType
from app.connectors.errors import ConnectorConnectionError
from app.connectors.prometheus import (
    PrometheusConnector,
    PrometheusConnectorConfig,
    PrometheusNotConnectedError,
    PrometheusQueryError,
    PrometheusTimeoutError,
    create_prometheus_connector,
    prometheus_response_to_metric_events,
)
from app.connectors.prometheus.client import HttpxPrometheusClient
from app.domain.events import MetricEvent


def _config(**overrides: object) -> PrometheusConnectorConfig:
    base = {
        "name": "metrics",
        "base_url": "http://prometheus:9090",
        "service": "payments-api",
        "environment": "production",
    }
    base.update(overrides)
    return PrometheusConnectorConfig(**base)


VECTOR_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {
                    "__name__": "http_requests_total",
                    "job": "api",
                    "instance": "10.0.0.1:8080",
                },
                "value": [1_726_780_800, "42"],
            }
        ],
    },
}

MATRIX_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"__name__": "cpu_usage", "pod": "api-1"},
                "values": [
                    [1_726_780_800, "0.5"],
                    [1_726_780_860, "0.7"],
                ],
            }
        ],
    },
}


class MockPrometheusHTTPClient:
    """In-memory Prometheus HTTP client for connector tests."""

    def __init__(
        self,
        handlers: dict[str, Callable[[dict[str, str] | None], dict[str, Any]]]
        | dict[str, dict[str, Any]],
    ) -> None:
        self._handlers = handlers
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((path, params))
        handler = self._handlers.get(path)
        if handler is None:
            msg = f"no mock response for {path}"
            raise ConnectorConnectionError(msg)
        if callable(handler):
            result = handler(params)
            if inspect.isawaitable(result):
                return await result
            return result
        return handler

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_test_connection_succeeds_with_mocked_query_response() -> None:
    client = MockPrometheusHTTPClient({"/api/v1/query": VECTOR_RESPONSE})
    connector = PrometheusConnector(_config(), client=client)

    result = await connector.test_connection()

    assert result.success is True
    assert result.detail == "ok"
    assert client.calls[0][0] == "/api/v1/query"
    assert client.calls[0][1] == {"query": "up"}


@pytest.mark.asyncio
async def test_test_connection_reports_prometheus_error_status() -> None:
    client = MockPrometheusHTTPClient(
        {
            "/api/v1/query": {
                "status": "error",
                "errorType": "bad_data",
                "error": "invalid query",
            }
        }
    )
    connector = PrometheusConnector(_config(), client=client)

    result = await connector.test_connection()

    assert result.success is False
    assert "invalid query" in result.detail


@pytest.mark.asyncio
async def test_connect_and_health_check_use_healthy_endpoint() -> None:
    client = MockPrometheusHTTPClient({"/-/healthy": {"status": "ok"}})
    connector = PrometheusConnector(_config(), client=client)

    await connector.connect()
    health = await connector.health_check()

    assert connector.state is ConnectorState.CONNECTED
    assert health.healthy is True
    assert "/-/healthy" in [call[0] for call in client.calls]


@pytest.mark.asyncio
async def test_query_converts_vector_response_to_metric_events() -> None:
    client = MockPrometheusHTTPClient(
        {
            "/-/healthy": {"status": "ok"},
            "/api/v1/query": VECTOR_RESPONSE,
        }
    )
    connector = PrometheusConnector(_config(), client=client)
    await connector.connect()

    events = await connector.query("http_requests_total")

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, MetricEvent)
    assert event.metric_name == "http_requests_total"
    assert event.value == 42.0
    assert event.labels == {"job": "api", "instance": "10.0.0.1:8080"}
    assert event.source == "prometheus:metrics"
    assert event.source_type == "prometheus"
    assert event.service == "payments-api"
    assert event.environment == "production"
    assert event.raw_data["query"] == "http_requests_total"


@pytest.mark.asyncio
async def test_query_range_converts_matrix_response_to_metric_events() -> None:
    client = MockPrometheusHTTPClient(
        {
            "/-/healthy": {"status": "ok"},
            "/api/v1/query_range": MATRIX_RESPONSE,
        }
    )
    connector = PrometheusConnector(_config(), client=client)
    await connector.connect()

    start = datetime(2025, 9, 20, 12, 0, tzinfo=UTC)
    end = datetime(2025, 9, 20, 12, 5, tzinfo=UTC)
    events = await connector.query_range(
        "cpu_usage",
        start=start,
        end=end,
        step="60s",
    )

    assert len(events) == 2
    assert events[0].metric_name == "cpu_usage"
    assert events[0].labels == {"pod": "api-1"}
    assert events[1].value == 0.7


@pytest.mark.asyncio
async def test_query_without_connect_raises_not_connected() -> None:
    connector = PrometheusConnector(_config())

    with pytest.raises(PrometheusNotConnectedError):
        await connector.query("up")


@pytest.mark.asyncio
async def test_query_raises_on_prometheus_error_payload() -> None:
    client = MockPrometheusHTTPClient(
        {
            "/-/healthy": {"status": "ok"},
            "/api/v1/query": {
                "status": "error",
                "errorType": "bad_data",
                "error": "parse error",
            },
        }
    )
    connector = PrometheusConnector(_config(), client=client)
    await connector.connect()

    with pytest.raises(PrometheusQueryError):
        await connector.query("bad{query")


def test_prometheus_response_to_metric_events_isolated_from_connector() -> None:
    events = prometheus_response_to_metric_events(
        response=VECTOR_RESPONSE,
        query="http_requests_total",
        source="prometheus:metrics",
        service="api",
        environment="staging",
    )

    assert len(events) == 1
    assert events[0].event_type.value == "METRIC"


@pytest.mark.asyncio
async def test_timeout_from_mock_client_surfaces_as_prometheus_timeout() -> None:
    async def _timeout(_params: dict[str, str] | None) -> dict[str, Any]:
        msg = "timed out"
        raise PrometheusTimeoutError(msg)

    client = MockPrometheusHTTPClient({"/api/v1/query": _timeout})
    connector = PrometheusConnector(_config(), client=client)

    result = await connector.test_connection()

    assert result.success is False
    assert "timed out" in result.detail


def test_registry_creates_prometheus_connector() -> None:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.PROMETHEUS, create_prometheus_connector)

    connector = registry.create(_config())

    assert isinstance(connector, PrometheusConnector)


@pytest.mark.asyncio
async def test_httpx_client_applies_bearer_authentication(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def get(self, path: str, params: dict[str, str] | None = None):
            request = httpx.Request("GET", f"http://prometheus:9090{path}")
            return httpx.Response(200, json={"status": "success"}, request=request)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.connectors.prometheus.client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    client = HttpxPrometheusClient(_config(bearer_token="secret-token"))
    await client.get_json("/api/v1/query", params={"query": "up"})
    await client.aclose()

    assert captured["headers"] == {"Authorization": "Bearer secret-token"}


@pytest.mark.asyncio
async def test_httpx_client_applies_basic_authentication(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def get(self, path: str, params: dict[str, str] | None = None):
            request = httpx.Request("GET", f"http://prometheus:9090{path}")
            return httpx.Response(200, json={"status": "success"}, request=request)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.connectors.prometheus.client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    client = HttpxPrometheusClient(
        _config(username="prom-user", password="prom-pass", bearer_token=None)
    )
    await client.get_json("/api/v1/query", params={"query": "up"})
    await client.aclose()

    assert captured["auth"] == ("prom-user", "prom-pass")
