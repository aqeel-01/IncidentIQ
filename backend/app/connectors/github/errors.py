"""GitHub connector errors."""

from __future__ import annotations

from app.connectors.errors import (
    ConnectorConnectionError,
    ConnectorError,
    ConnectorNotConnectedError,
)


class GitHubError(ConnectorError):
    """Base error for GitHub connector operations."""


class GitHubNotConnectedError(ConnectorNotConnectedError):
    """Raised when a query runs without an active client session."""


class GitHubTimeoutError(GitHubError, ConnectorConnectionError):
    """Raised when a GitHub HTTP request exceeds the configured timeout."""


class GitHubQueryError(GitHubError):
    """Raised when the GitHub API returns an error response."""


class GitHubAuthenticationError(GitHubError, ConnectorConnectionError):
    """Raised when GitHub rejects the configured credentials."""
