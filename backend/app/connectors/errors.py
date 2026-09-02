"""Connector-specific errors."""

from __future__ import annotations


class ConnectorError(Exception):
    """Base error for connector operations."""


class ConnectorNotConnectedError(ConnectorError):
    """Raised when an operation requires an active connection."""


class ConnectorConnectionError(ConnectorError):
    """Raised when connect or test_connection fails."""


class ConnectorRegistrationError(ConnectorError):
    """Raised when a connector type is unknown or already registered."""
