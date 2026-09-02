"""HTTP client for Azure DevOps API access."""

from __future__ import annotations

import base64
import re
from typing import Any, Protocol

import httpx

from app.connectors.azure_devops.config import AzureDevOpsConnectorConfig
from app.connectors.azure_devops.errors import (
    AzureDevOpsAuthenticationError,
    AzureDevOpsTimeoutError,
)
from app.connectors.errors import ConnectorConnectionError

_CREDENTIAL_PATTERN = re.compile(
    r"(Basic\s+[A-Za-z0-9+/=]+|"
    r"[A-Za-z0-9]{52}|"
    r"personal_access_token[=:]\s*\S+)",
    re.IGNORECASE,
)


def sanitize_error_message(message: str) -> str:
    """Redact credential-like values from error messages."""

    return _CREDENTIAL_PATTERN.sub("***", message)


class AzureDevOpsHTTPClient(Protocol):
    """Minimal HTTP surface used by :class:`AzureDevOpsConnector`."""

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any: ...

    async def aclose(self) -> None: ...


def build_auth_headers(config: AzureDevOpsConnectorConfig) -> dict[str, str]:
    """Build Azure DevOps API headers using PAT basic authentication."""

    headers = {"Accept": "application/json"}
    if config.personal_access_token is not None:
        token = config.personal_access_token.get_secret_value()
        encoded = base64.b64encode(f":{token}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    return headers


class HttpxAzureDevOpsClient:
    """Async Azure DevOps HTTP client backed by ``httpx``."""

    def __init__(self, config: AzureDevOpsConnectorConfig) -> None:
        self._timeout_seconds = config.timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=config.organization_base_url,
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
                "azure devops request timed out after "
                f"{self._timeout_seconds} seconds"
            )
            raise AzureDevOpsTimeoutError(msg) from exc
        except httpx.HTTPStatusError as exc:
            msg = sanitize_error_message(f"azure devops request failed: {exc}")
            if exc.response.status_code in {401, 403}:
                raise AzureDevOpsAuthenticationError(msg) from exc
            raise ConnectorConnectionError(msg) from exc
        except httpx.HTTPError as exc:
            msg = sanitize_error_message(f"azure devops request failed: {exc}")
            raise ConnectorConnectionError(msg) from exc

        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
