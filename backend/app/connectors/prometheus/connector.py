"""Prometheus connector implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.connectors.base import Connector
from app.connectors.errors import ConnectorConnectionError
from app.connectors.prometheus.client import HttpxPrometheusClient, PrometheusHTTPClient
from app.connectors.prometheus.config import PrometheusConnectorConfig
from app.connectors.prometheus.convert import prometheus_response_to_metric_events
from app.connectors.prometheus.errors import (
    PrometheusNotConnectedError,
    PrometheusQueryError,
    PrometheusTimeoutError,
)
from app.connectors.types import (
    ConnectionTestResult,
    ConnectorState,
    HealthCheckResult,
)
from app.domain.events import MetricEvent


class PrometheusConnector(Connector):
    """Connector for Prometheus metrics via the HTTP API."""

    def __init__(
        self,
        config: PrometheusConnectorConfig,
        *,
        client: PrometheusHTTPClient | None = None,
    ) -> None:
        super().__init__(config)
        self._prometheus_config = config
        self._client = client
        self._owns_client = client is None

    @property
    def prometheus_config(self) -> PrometheusConnectorConfig:
        return self._prometheus_config

    def _source(self) -> str:
        return f"prometheus:{self.name}"

    async def connect(self) -> None:
        if self._client is None:
            self._client = HttpxPrometheusClient(self._prometheus_config)
            self._owns_client = True
        try:
            await self._client.get_json("/-/healthy")
            self._state = ConnectorState.CONNECTED
        except (PrometheusTimeoutError, ConnectorConnectionError) as exc:
            self._state = ConnectorState.ERROR
            raise ConnectorConnectionError(str(exc)) from exc

    async def disconnect(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._state = ConnectorState.DISCONNECTED

    async def health_check(self) -> HealthCheckResult:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            return HealthCheckResult(
                connector_type=self.connector_type,
                name=self.name,
                healthy=False,
                state=self.state,
                detail="not connected",
            )
        try:
            await self._client.get_json("/-/healthy")
            detail = "ok"
            healthy = True
        except PrometheusTimeoutError as exc:
            detail = str(exc)
            healthy = False
        except ConnectorConnectionError as exc:
            detail = str(exc)
            healthy = False

        return HealthCheckResult(
            connector_type=self.connector_type,
            name=self.name,
            healthy=healthy,
            state=self.state,
            detail=detail,
        )

    async def test_connection(self) -> ConnectionTestResult:
        probe_client = self._client
        created_probe = False
        if probe_client is None:
            probe_client = HttpxPrometheusClient(self._prometheus_config)
            created_probe = True

        try:
            response = await probe_client.get_json(
                "/api/v1/query",
                params={"query": "up"},
            )
            success = response.get("status") == "success"
            detail = "ok" if success else str(response.get("error", "query failed"))
        except PrometheusTimeoutError as exc:
            success = False
            detail = str(exc)
        except ConnectorConnectionError as exc:
            success = False
            detail = str(exc)
        finally:
            if created_probe:
                await probe_client.aclose()

        return ConnectionTestResult(
            connector_type=self.connector_type,
            name=self.name,
            success=success,
            detail=detail,
        )

    async def query(
        self,
        promql: str,
        *,
        at: datetime | None = None,
    ) -> list[MetricEvent]:
        """Run an instant PromQL query and return canonical metric events."""

        client = self._require_client()
        params: dict[str, str] = {"query": promql}
        if at is not None:
            params["time"] = str(at.astimezone(UTC).timestamp())

        response = await self._execute_query(client, "/api/v1/query", params, promql)
        return prometheus_response_to_metric_events(
            response=response,
            query=promql,
            source=self._source(),
            service=self._prometheus_config.service,
            environment=self._prometheus_config.environment,
        )

    async def query_range(
        self,
        promql: str,
        *,
        start: datetime,
        end: datetime,
        step: str,
    ) -> list[MetricEvent]:
        """Run a range PromQL query and return canonical metric events."""

        client = self._require_client()
        params = {
            "query": promql,
            "start": str(start.astimezone(UTC).timestamp()),
            "end": str(end.astimezone(UTC).timestamp()),
            "step": step,
        }
        response = await self._execute_query(
            client,
            "/api/v1/query_range",
            params,
            promql,
        )
        return prometheus_response_to_metric_events(
            response=response,
            query=promql,
            source=self._source(),
            service=self._prometheus_config.service,
            environment=self._prometheus_config.environment,
        )

    def _require_client(self) -> PrometheusHTTPClient:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            raise PrometheusNotConnectedError("prometheus connector is not connected")
        return self._client

    async def _execute_query(
        self,
        client: PrometheusHTTPClient,
        path: str,
        params: dict[str, str],
        promql: str,
    ) -> dict[str, Any]:
        try:
            response = await client.get_json(path, params=params)
        except PrometheusTimeoutError:
            raise
        except ConnectorConnectionError as exc:
            raise PrometheusQueryError(str(exc)) from exc

        if response.get("status") != "success":
            error_type = response.get("errorType", "unknown")
            error = response.get("error", "prometheus query failed")
            msg = f"prometheus query {promql!r} failed: {error_type}: {error}"
            raise PrometheusQueryError(msg)
        return response


def create_prometheus_connector(
    config: PrometheusConnectorConfig,
) -> PrometheusConnector:
    """Factory used by :class:`~app.connectors.registry.ConnectorRegistry`."""

    return PrometheusConnector(config)
