"""GitHub connector."""

from app.connectors.github.client import build_auth_headers, sanitize_error_message
from app.connectors.github.config import GitHubConnectorConfig
from app.connectors.github.connector import GitHubConnector, create_github_connector
from app.connectors.github.convert import (
    github_deployment_to_event,
    github_release_to_event,
)
from app.connectors.github.errors import (
    GitHubAuthenticationError,
    GitHubError,
    GitHubNotConnectedError,
    GitHubQueryError,
    GitHubTimeoutError,
)
from app.connectors.github.types import (
    GitHubChangedFile,
    GitHubCommit,
    GitHubDeployment,
    GitHubPullRequest,
    GitHubRelease,
    GitHubRepository,
)

__all__ = [
    "GitHubAuthenticationError",
    "GitHubChangedFile",
    "GitHubCommit",
    "GitHubConnector",
    "GitHubConnectorConfig",
    "GitHubDeployment",
    "GitHubError",
    "GitHubNotConnectedError",
    "GitHubPullRequest",
    "GitHubQueryError",
    "GitHubRelease",
    "GitHubRepository",
    "GitHubTimeoutError",
    "build_auth_headers",
    "create_github_connector",
    "github_deployment_to_event",
    "github_release_to_event",
    "sanitize_error_message",
]
