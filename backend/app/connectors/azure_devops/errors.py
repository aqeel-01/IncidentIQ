"""Azure DevOps connector errors."""

from __future__ import annotations

from app.connectors.errors import (
    ConnectorConnectionError,
    ConnectorError,
    ConnectorNotConnectedError,
)


class AzureDevOpsError(ConnectorError):
    """Base error for Azure DevOps connector operations."""


class AzureDevOpsNotConnectedError(ConnectorNotConnectedError):
    """Raised when a query runs without an active client session."""


class AzureDevOpsTimeoutError(AzureDevOpsError, ConnectorConnectionError):
    """Raised when an Azure DevOps HTTP request exceeds the configured timeout."""


class AzureDevOpsQueryError(AzureDevOpsError):
    """Raised when the Azure DevOps API returns an error response."""


class AzureDevOpsAuthenticationError(AzureDevOpsError, ConnectorConnectionError):
    """Raised when Azure DevOps rejects the configured credentials."""
