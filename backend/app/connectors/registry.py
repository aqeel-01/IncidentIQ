"""Connector factory registry for pluggable source implementations."""

from __future__ import annotations

from collections.abc import Callable

from app.connectors.base import Connector
from app.connectors.errors import ConnectorRegistrationError
from app.connectors.types import ConnectorConfig, ConnectorType

ConnectorFactory = Callable[[ConnectorConfig], Connector]


class ConnectorRegistry:
    """Register and instantiate connector implementations by type."""

    def __init__(self) -> None:
        self._factories: dict[ConnectorType, ConnectorFactory] = {}

    def register(
        self,
        connector_type: ConnectorType,
        factory: ConnectorFactory,
        *,
        replace: bool = False,
    ) -> None:
        if connector_type in self._factories and not replace:
            msg = f"connector type {connector_type!r} is already registered"
            raise ConnectorRegistrationError(msg)
        self._factories[connector_type] = factory

    def create(self, config: ConnectorConfig) -> Connector:
        factory = self._factories.get(config.connector_type)
        if factory is None:
            msg = f"no connector registered for type {config.connector_type!r}"
            raise ConnectorRegistrationError(msg)
        return factory(config)

    def is_registered(self, connector_type: ConnectorType) -> bool:
        return connector_type in self._factories

    def supported_types(self) -> frozenset[ConnectorType]:
        return frozenset(self._factories)
