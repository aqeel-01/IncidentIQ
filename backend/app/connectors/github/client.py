"""HTTP client for GitHub API access."""

from __future__ import annotations

import re
from typing import Any, Protocol

import httpx

from app.connectors.errors import ConnectorConnectionError
from app.connectors.github.config import GitHubConnectorConfig
from app.connectors.github.errors import (
    GitHubAuthenticationError,
    GitHubTimeoutError,
)

_TOKEN_PATTERN = re.compile(
    r"(gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|Bearer\s+\S+|token\s+\S+)",
    re.IGNORECASE,
)


def sanitize_error_message(message: str) -> str:
    """Redact credential-like values from error messages."""

    return _TOKEN_PATTERN.sub("***", message)


class GitHubHTTPClient(Protocol):
    """Minimal HTTP surface used by :class:`GitHubConnector`."""

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any: ...

    async def aclose(self) -> None: ...


def build_auth_headers(config: GitHubConnectorConfig) -> dict[str, str]:
    """Build GitHub API headers without logging credential values."""

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if config.token is not None:
        scheme = "Bearer" if config.auth_scheme == "bearer" else "token"
        headers["Authorization"] = f"{scheme} {config.token.get_secret_value()}"
    return headers


class HttpxGitHubClient:
    """Async GitHub HTTP client backed by ``httpx``."""

    def __init__(self, config: GitHubConnectorConfig) -> None:
        self._timeout_seconds = config.timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=config.normalized_base_url,
            headers=build_auth_headers(config),
            timeout=config.timeout_seconds,
            verify=config.verify_tls,
        )

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any:
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = sanitize_error_message(
                f"github request timed out after {self._timeout_seconds} seconds"
            )
            raise GitHubTimeoutError(msg) from exc
        except httpx.HTTPStatusError as exc:
            msg = sanitize_error_message(f"github request failed: {exc}")
            if exc.response.status_code in {401, 403}:
                raise GitHubAuthenticationError(msg) from exc
            raise ConnectorConnectionError(msg) from exc
        except httpx.HTTPError as exc:
            msg = sanitize_error_message(f"github request failed: {exc}")
            raise ConnectorConnectionError(msg) from exc

        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
