"""Connector interface and lifecycle contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.connectors.types import (
    ConnectionTestResult,
    ConnectorConfig,
    ConnectorState,
    ConnectorType,
    HealthCheckResult,
)


class Connector(ABC):
    """Abstract connector for external incident data sources.

    Connectors live outside the investigation engine. They are responsible only
    for establishing and validating access to a source system. Downstream pipeline
    stages consume canonical events produced by concrete implementations.
    """

    def __init__(self, config: ConnectorConfig) -> None:
        self._config = config
        self._state = ConnectorState.DISCONNECTED

    @property
    def config(self) -> ConnectorConfig:
        return self._config

    @property
    def connector_type(self) -> ConnectorType:
        return self._config.connector_type

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def state(self) -> ConnectorState:
        return self._state

    @abstractmethod
    async def connect(self) -> None:
        """Open a reusable connection/session to the external source."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the active connection/session and release resources."""

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        """Check health of the current connector session."""

    @abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """Probe connectivity without requiring a persistent session."""

    async def __aenter__(self) -> Connector:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.disconnect()
