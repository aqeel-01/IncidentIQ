"""HTTP client for Prometheus API access."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.connectors.errors import ConnectorConnectionError
from app.connectors.prometheus.config import PrometheusConnectorConfig
from app.connectors.prometheus.errors import PrometheusTimeoutError
from app.core.security import sanitize_error_message


class PrometheusHTTPClient(Protocol):
    """Minimal HTTP surface used by :class:`PrometheusConnector`."""

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


class HttpxPrometheusClient:
    """Async Prometheus HTTP client backed by ``httpx``."""

    def __init__(self, config: PrometheusConnectorConfig) -> None:
        headers: dict[str, str] = {}
        auth: httpx.Auth | tuple[str, str] | None = None
        if config.bearer_token:
            headers["Authorization"] = f"Bearer {config.bearer_token}"
        elif config.username and config.password:
            auth = (config.username, config.password)

        self._timeout_seconds = config.timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=config.normalized_base_url,
            headers=headers,
            auth=auth,
            timeout=config.timeout_seconds,
            verify=config.verify_tls,
        )

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = (
                f"prometheus request timed out after "
                f"{self._timeout_seconds} seconds"
            )
            raise PrometheusTimeoutError(msg) from exc
        except httpx.HTTPError as exc:
            msg = sanitize_error_message(f"prometheus request failed: {exc}")
            raise ConnectorConnectionError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            msg = "prometheus response must be a JSON object"
            raise ConnectorConnectionError(msg)
        return payload

    async def aclose(self) -> None:
        await self._client.aclose()
