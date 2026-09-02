"""Shared connector for Elasticsearch-compatible search backends."""

from __future__ import annotations

from typing import Any

from app.connectors.base import Connector
from app.connectors.errors import ConnectorConnectionError
from app.connectors.search.client import HttpxSearchClient, SearchHTTPClient
from app.connectors.search.config import SearchIndexConnectorConfig
from app.connectors.search.convert import search_response_to_log_events
from app.connectors.search.errors import (
    SearchIndexNotConnectedError,
    SearchIndexQueryError,
    SearchIndexTimeoutError,
)
from app.connectors.search.profile import SearchConnectorProfile
from app.connectors.search.query import build_log_search_body, search_path_for_index
from app.connectors.search.types import LogQueryFilters
from app.connectors.types import (
    ConnectionTestResult,
    ConnectorState,
    HealthCheckResult,
)
from app.domain.events import LogEvent


class SearchIndexConnector(Connector):
    """Connector for log indices exposed via the search HTTP API."""

    def __init__(
        self,
        config: SearchIndexConnectorConfig,
        *,
        profile: SearchConnectorProfile,
        client: SearchHTTPClient | None = None,
        not_connected_error: type[SearchIndexNotConnectedError] = (
            SearchIndexNotConnectedError
        ),
        timeout_error: type[SearchIndexTimeoutError] = SearchIndexTimeoutError,
        query_error: type[SearchIndexQueryError] = SearchIndexQueryError,
    ) -> None:
        super().__init__(config)
        self._search_config = config
        self._profile = profile
        self._client = client
        self._owns_client = client is None
        self._not_connected_error = not_connected_error
        self._timeout_error = timeout_error
        self._query_error = query_error

    @property
    def search_config(self) -> SearchIndexConnectorConfig:
        return self._search_config

    def _source(self) -> str:
        return f"{self._profile.source_prefix}:{self.name}"

    async def connect(self) -> None:
        if self._client is None:
            self._client = HttpxSearchClient(
                self._search_config,
                system_name=self._profile.system_name,
                timeout_error=self._timeout_error,
            )
            self._owns_client = True
        try:
            await self._client.get_json("/_cluster/health")
            self._state = ConnectorState.CONNECTED
        except (self._timeout_error, ConnectorConnectionError) as exc:
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
            response = await self._client.get_json("/_cluster/health")
            status = str(response.get("status", "")).lower()
            healthy = status in {"green", "yellow"}
            detail = status or "unknown"
        except self._timeout_error as exc:
            healthy = False
            detail = str(exc)
        except ConnectorConnectionError as exc:
            healthy = False
            detail = str(exc)

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
            probe_client = HttpxSearchClient(
                self._search_config,
                system_name=self._profile.system_name,
                timeout_error=self._timeout_error,
            )
            created_probe = True

        try:
            response = await probe_client.get_json("/_cluster/health")
            status = str(response.get("status", "")).lower()
            success = status in {"green", "yellow", "red"}
            detail = status or "unknown"
        except self._timeout_error as exc:
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

    async def search_logs(
        self,
        filters: LogQueryFilters,
        *,
        index: str | None = None,
    ) -> list[LogEvent]:
        """Query logs from the configured index and return canonical events."""

        client = self._require_client()
        target_index = index or self._search_config.index
        body = build_log_search_body(filters, self._search_config)
        response = await self._execute_search(
            client,
            search_path_for_index(target_index),
            body,
        )
        return search_response_to_log_events(
            response,
            config=self._search_config,
            source_name=self._source(),
            source_type=self._profile.source_type,
        )

    def _require_client(self) -> SearchHTTPClient:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            msg = f"{self._profile.system_name} connector is not connected"
            raise self._not_connected_error(msg)
        return self._client

    async def _execute_search(
        self,
        client: SearchHTTPClient,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await client.post_json(path, body=body)
        except self._timeout_error:
            raise
        except ConnectorConnectionError as exc:
            raise self._query_error(str(exc)) from exc

        if response.get("timed_out"):
            msg = f"{self._profile.system_name} search timed out"
            raise self._query_error(msg)
        if "error" in response:
            raise self._query_error(str(response["error"]))
        return response
