"""Prometheus connector errors."""

from __future__ import annotations

from app.connectors.errors import (
    ConnectorConnectionError,
    ConnectorError,
    ConnectorNotConnectedError,
)


class PrometheusError(ConnectorError):
    """Base error for Prometheus connector operations."""


class PrometheusNotConnectedError(ConnectorNotConnectedError):
    """Raised when a query runs without an active client session."""


class PrometheusTimeoutError(PrometheusError, ConnectorConnectionError):
    """Raised when a Prometheus HTTP request exceeds the configured timeout."""


class PrometheusQueryError(PrometheusError):
    """Raised when Prometheus returns an error response for a query."""
