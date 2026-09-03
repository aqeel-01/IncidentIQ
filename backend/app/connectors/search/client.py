"""HTTP client for Elasticsearch-compatible search APIs."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.connectors.errors import ConnectorConnectionError
from app.connectors.search.config import SearchIndexConnectorConfig
from app.connectors.search.errors import SearchIndexTimeoutError
from app.core.security import sanitize_error_message


class SearchHTTPClient(Protocol):
    """Minimal HTTP surface used by :class:`SearchIndexConnector`."""

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    async def post_json(
        self,
        path: str,
        *,
        body: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


class HttpxSearchClient:
    """Async search HTTP client backed by ``httpx``."""

    def __init__(
        self,
        config: SearchIndexConnectorConfig,
        *,
        system_name: str,
        timeout_error: type[SearchIndexTimeoutError] = SearchIndexTimeoutError,
    ) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth: httpx.Auth | tuple[str, str] | None = None
        if config.bearer_token:
            headers["Authorization"] = f"Bearer {config.bearer_token}"
        elif config.username and config.password:
            auth = (config.username, config.password)

        self._system_name = system_name
        self._timeout_error = timeout_error
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
        return await self._request("GET", path, params=params)

    async def post_json(
        self,
        path: str,
        *,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request("POST", path, json_body=body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(
                method, path, params=params, json=json_body
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = (
                f"{self._system_name} request timed out after "
                f"{self._timeout_seconds} seconds"
            )
            raise self._timeout_error(msg) from exc
        except httpx.HTTPError as exc:
            msg = sanitize_error_message(
                f"{self._system_name} request failed: {exc}"
            )
            raise ConnectorConnectionError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            msg = f"{self._system_name} response must be a JSON object"
            raise ConnectorConnectionError(msg)
        return payload

    async def aclose(self) -> None:
        await self._client.aclose()
