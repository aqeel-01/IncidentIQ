"""Mocked integration tests for the Elasticsearch connector."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.connectors import (
    ConnectorRegistry,
    ConnectorState,
    ConnectorType,
    default_connector_registry,
)
from app.connectors.elasticsearch import (
    ElasticsearchConnector,
    ElasticsearchConnectorConfig,
    ElasticsearchNotConnectedError,
    ElasticsearchTimeoutError,
    LogQueryFilters,
    build_log_search_body,
    create_elasticsearch_connector,
    elasticsearch_response_to_log_events,
)
from app.connectors.elasticsearch.client import HttpxElasticsearchClient
from app.connectors.errors import ConnectorConnectionError
from app.db.models.enums import Severity
from app.domain.events import LogEvent


def _config(**overrides: object) -> ElasticsearchConnectorConfig:
    base = {
        "name": "logs",
        "base_url": "http://elasticsearch:9200",
        "index": "app-logs-*",
        "default_service": "payments-api",
        "default_environment": "production",
    }
    base.update(overrides)
    return ElasticsearchConnectorConfig(**base)


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, minutes, tzinfo=UTC)


HEALTH_RESPONSE = {"status": "green", "cluster_name": "incidentiq"}

SEARCH_RESPONSE = {
    "took": 3,
    "timed_out": False,
    "hits": {
        "total": {"value": 1, "relation": "eq"},
        "hits": [
            {
                "_index": "app-logs-2026.09.01",
                "_id": "doc-1",
                "_source": {
                    "@timestamp": "2026-09-01T12:00:00Z",
                    "message": "connection refused",
                    "service": "payments-api",
                    "environment": "production",
                    "severity": "error",
                    "host": "api-1",
                },
            }
        ],
    },
}


class MockElasticsearchHTTPClient:
    """In-memory Elasticsearch HTTP client for connector tests."""

    def __init__(
        self,
        get_handlers: dict[str, Callable[[dict[str, str] | None], dict[str, Any]]]
        | dict[str, dict[str, Any]]
        | None = None,
        post_handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]]
        | dict[str, dict[str, Any]]
        | None = None,
    ) -> None:
        self.get_handlers = get_handlers or {}
        self.post_handlers = post_handlers or {}
        self.get_calls: list[tuple[str, dict[str, str] | None]] = []
        self.post_calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.get_calls.append((path, params))
        handler = self.get_handlers.get(path)
        if handler is None:
            msg = f"no mock GET response for {path}"
            raise ConnectorConnectionError(msg)
        if callable(handler):
            result = handler(params)
            if inspect.isawaitable(result):
                return await result
            return result
        return handler

    async def post_json(
        self,
        path: str,
        *,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        self.post_calls.append((path, body))
        handler = self.post_handlers.get(path)
        if handler is None:
            msg = f"no mock POST response for {path}"
            raise ConnectorConnectionError(msg)
        if callable(handler):
            result = handler(body)
            if inspect.isawaitable(result):
                return await result
            return result
        return handler

    async def aclose(self) -> None:
        return None


def test_build_log_search_body_applies_time_and_attribute_filters() -> None:
    config = _config()
    body = build_log_search_body(
        LogQueryFilters(
            start=_ts(0),
            end=_ts(30),
            service="payments-api",
            environment="production",
            severity=Severity.HIGH,
            size=250,
        ),
        config,
    )

    filters = body["query"]["bool"]["filter"]
    assert body["size"] == 250
    range_filter = {
        "range": {
            "@timestamp": {
                "gte": _ts(0).isoformat(),
                "lte": _ts(30).isoformat(),
            }
        }
    }
    assert range_filter in filters
    assert {"term": {"service": "payments-api"}} in filters
    assert {"term": {"environment": "production"}} in filters
    assert {"terms": {"severity": ["high", "error", "err"]}} in filters


def test_elasticsearch_response_to_log_events_maps_hits() -> None:
    events = elasticsearch_response_to_log_events(
        SEARCH_RESPONSE,
        config=_config(),
        source_name="elasticsearch:logs",
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, LogEvent)
    assert event.message == "connection refused"
    assert event.severity is Severity.HIGH
    assert event.service == "payments-api"
    assert event.source == "elasticsearch:logs"
    assert event.source_type == "elasticsearch"
    assert event.raw_data["_id"] == "doc-1"


@pytest.mark.asyncio
async def test_test_connection_succeeds_with_mocked_cluster_health() -> None:
    client = MockElasticsearchHTTPClient(
        get_handlers={"/_cluster/health": HEALTH_RESPONSE},
    )
    connector = ElasticsearchConnector(_config(), client=client)

    result = await connector.test_connection()

    assert result.success is True
    assert result.detail == "green"


@pytest.mark.asyncio
async def test_connect_and_health_check_use_cluster_health() -> None:
    client = MockElasticsearchHTTPClient(
        get_handlers={"/_cluster/health": HEALTH_RESPONSE},
    )
    connector = ElasticsearchConnector(_config(), client=client)

    await connector.connect()
    health = await connector.health_check()

    assert connector.state is ConnectorState.CONNECTED
    assert health.healthy is True
    assert health.detail == "green"


@pytest.mark.asyncio
async def test_search_logs_uses_index_and_returns_log_events() -> None:
    client = MockElasticsearchHTTPClient(
        get_handlers={"/_cluster/health": HEALTH_RESPONSE},
        post_handlers={"/app-logs-*/_search": SEARCH_RESPONSE},
    )
    connector = ElasticsearchConnector(_config(), client=client)
    await connector.connect()

    events = await connector.search_logs(
        LogQueryFilters(start=_ts(0), end=_ts(10), severity=Severity.HIGH)
    )

    assert len(events) == 1
    assert client.post_calls[0][0] == "/app-logs-*/_search"
    body = client.post_calls[0][1]
    assert body["query"]["bool"]["filter"]


@pytest.mark.asyncio
async def test_search_logs_supports_index_override() -> None:
    client = MockElasticsearchHTTPClient(
        get_handlers={"/_cluster/health": HEALTH_RESPONSE},
        post_handlers={"/custom-index/_search": SEARCH_RESPONSE},
    )
    connector = ElasticsearchConnector(_config(), client=client)
    await connector.connect()

    await connector.search_logs(
        LogQueryFilters(start=_ts(0), end=_ts(10)),
        index="custom-index",
    )

    assert client.post_calls[0][0] == "/custom-index/_search"


@pytest.mark.asyncio
async def test_search_logs_without_connect_raises_not_connected() -> None:
    connector = ElasticsearchConnector(_config())

    with pytest.raises(ElasticsearchNotConnectedError):
        await connector.search_logs(LogQueryFilters(start=_ts(0), end=_ts(10)))


@pytest.mark.asyncio
async def test_timeout_from_mock_client_surfaces_on_test_connection() -> None:
    async def _timeout(_params: dict[str, str] | None) -> dict[str, Any]:
        msg = "timed out"
        raise ElasticsearchTimeoutError(msg)

    client = MockElasticsearchHTTPClient(get_handlers={"/_cluster/health": _timeout})
    connector = ElasticsearchConnector(_config(), client=client)

    result = await connector.test_connection()

    assert result.success is False
    assert "timed out" in result.detail


def test_registry_creates_elasticsearch_connector() -> None:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.ELASTICSEARCH, create_elasticsearch_connector)

    connector = registry.create(_config())

    assert isinstance(connector, ElasticsearchConnector)


def test_default_registry_includes_elasticsearch() -> None:
    registry = default_connector_registry()
    connector = registry.create(_config())

    assert isinstance(connector, ElasticsearchConnector)


@pytest.mark.asyncio
async def test_httpx_client_applies_bearer_authentication(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def request(self, method: str, path: str, **kwargs: object):
            request = httpx.Request(method, f"http://elasticsearch:9200{path}")
            return httpx.Response(200, json=HEALTH_RESPONSE, request=request)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.connectors.search.client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    client = HttpxElasticsearchClient(_config(bearer_token="secret-token"))
    await client.get_json("/_cluster/health")
    await client.aclose()

    assert captured["headers"]["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_httpx_client_applies_basic_authentication(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def request(self, method: str, path: str, **kwargs: object):
            request = httpx.Request(method, f"http://elasticsearch:9200{path}")
            return httpx.Response(200, json=HEALTH_RESPONSE, request=request)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.connectors.search.client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    client = HttpxElasticsearchClient(
        _config(username="es-user", password="es-pass", bearer_token=None)
    )
    await client.get_json("/_cluster/health")
    await client.aclose()

    assert captured["auth"] == ("es-user", "es-pass")
