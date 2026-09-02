"""Interface tests for the generic connector architecture."""

from __future__ import annotations

import inspect

import pytest

from app.connectors import (
    ConnectionTestResult,
    Connector,
    ConnectorConfig,
    ConnectorConnectionError,
    ConnectorRegistry,
    ConnectorState,
    ConnectorType,
    HealthCheckResult,
)
from app.connectors.errors import ConnectorRegistrationError


class StubConnector(Connector):
    """Minimal in-memory connector used to exercise the interface contract."""

    def __init__(
        self,
        config: ConnectorConfig,
        *,
        connect_succeeds: bool = True,
        test_succeeds: bool = True,
        health_when_connected: bool = True,
    ) -> None:
        super().__init__(config)
        self.connect_succeeds = connect_succeeds
        self.test_succeeds = test_succeeds
        self.health_when_connected = health_when_connected
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1
        if not self.connect_succeeds:
            self._state = ConnectorState.ERROR
            msg = "stub connect failed"
            raise ConnectorConnectionError(msg)
        self._state = ConnectorState.CONNECTED

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._state = ConnectorState.DISCONNECTED

    async def health_check(self) -> HealthCheckResult:
        if self.state is not ConnectorState.CONNECTED:
            return HealthCheckResult(
                connector_type=self.connector_type,
                name=self.name,
                healthy=False,
                state=self.state,
                detail="not connected",
            )
        return HealthCheckResult(
            connector_type=self.connector_type,
            name=self.name,
            healthy=self.health_when_connected,
            state=self.state,
            detail="ok" if self.health_when_connected else "unhealthy",
        )

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            connector_type=self.connector_type,
            name=self.name,
            success=self.test_succeeds,
            detail="ok" if self.test_succeeds else "probe failed",
        )


def _config(
    connector_type: ConnectorType = ConnectorType.OPENSEARCH,
    name: str = "payments-opensearch",
) -> ConnectorConfig:
    return ConnectorConfig(connector_type=connector_type, name=name)


def test_connector_interface_defines_required_async_methods() -> None:
    required = {"connect", "disconnect", "health_check", "test_connection"}
    assert required.issubset(Connector.__abstractmethods__)

    for method_name in required:
        method = getattr(Connector, method_name)
        assert inspect.iscoroutinefunction(method)


def test_connector_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Connector(_config())  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_connector_lifecycle_connect_health_disconnect() -> None:
    connector = StubConnector(_config(ConnectorType.PROMETHEUS, "metrics"))

    assert connector.state is ConnectorState.DISCONNECTED

    await connector.connect()
    assert connector.state is ConnectorState.CONNECTED
    assert connector.connect_calls == 1

    health = await connector.health_check()
    assert isinstance(health, HealthCheckResult)
    assert health.healthy is True
    assert health.connector_type is ConnectorType.PROMETHEUS

    await connector.disconnect()
    assert connector.state is ConnectorState.DISCONNECTED
    assert connector.disconnect_calls == 1


@pytest.mark.asyncio
async def test_health_check_reports_unhealthy_when_disconnected() -> None:
    connector = StubConnector(_config())

    health = await connector.health_check()

    assert health.healthy is False
    assert health.state is ConnectorState.DISCONNECTED
    assert health.detail == "not connected"


@pytest.mark.asyncio
async def test_test_connection_runs_without_persistent_session() -> None:
    connector = StubConnector(_config(ConnectorType.GITHUB, "repo-events"))

    result = await connector.test_connection()

    assert isinstance(result, ConnectionTestResult)
    assert result.success is True
    assert connector.state is ConnectorState.DISCONNECTED
    assert connector.connect_calls == 0


@pytest.mark.asyncio
async def test_connect_failure_sets_error_state() -> None:
    connector = StubConnector(_config(), connect_succeeds=False)

    with pytest.raises(ConnectorConnectionError):
        await connector.connect()

    assert connector.state is ConnectorState.ERROR


@pytest.mark.asyncio
async def test_async_context_manager_runs_connect_and_disconnect() -> None:
    config = _config(ConnectorType.AZURE_DEVOPS, "pipelines")
    async with StubConnector(config) as connector:
        assert connector.state is ConnectorState.CONNECTED
    assert connector.disconnect_calls == 1
    assert connector.state is ConnectorState.DISCONNECTED


def test_registry_creates_registered_connector() -> None:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.DATABASE, StubConnector)

    connector = registry.create(_config(ConnectorType.DATABASE, "warehouse"))

    assert isinstance(connector, StubConnector)
    assert connector.connector_type is ConnectorType.DATABASE


def test_registry_rejects_unknown_connector_type() -> None:
    registry = ConnectorRegistry()

    with pytest.raises(ConnectorRegistrationError):
        registry.create(_config(ConnectorType.ELASTICSEARCH))


def test_registry_prevents_duplicate_registration_by_default() -> None:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.OPENSEARCH, StubConnector)

    with pytest.raises(ConnectorRegistrationError):
        registry.register(ConnectorType.OPENSEARCH, StubConnector)


def test_supported_connector_types_cover_planned_providers() -> None:
    planned = {
        ConnectorType.OPENSEARCH,
        ConnectorType.ELASTICSEARCH,
        ConnectorType.DATABASE,
        ConnectorType.PROMETHEUS,
        ConnectorType.GITHUB,
        ConnectorType.AZURE_DEVOPS,
    }
    assert planned.issubset(set(ConnectorType))


def test_connectors_package_is_isolated_from_investigation_domain() -> None:
    import app.connectors as connectors_pkg
    import app.domain as domain_pkg

    connectors_path = connectors_pkg.__file__ or ""
    domain_path = domain_pkg.__file__ or ""

    assert "connectors" in connectors_path
    assert "domain" in domain_path
    assert connectors_path != domain_path

    # Domain investigation code must not depend on connector implementations.
    import app.domain.ingestion as ingestion

    source = inspect.getsource(ingestion)
    assert "app.connectors" not in source
