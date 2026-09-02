"""Azure DevOps connector configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, HttpUrl, SecretStr

from app.connectors.types import ConnectorConfig, ConnectorType


class AzureDevOpsConnectorConfig(ConnectorConfig):
    """Configuration for an Azure DevOps connector."""

    connector_type: Literal[ConnectorType.AZURE_DEVOPS] = ConnectorType.AZURE_DEVOPS
    organization: str = Field(min_length=1)
    base_url: HttpUrl | str = Field(default="https://dev.azure.com")
    api_version: str = Field(default="7.1", min_length=1)
    personal_access_token: SecretStr | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    verify_tls: bool = True
    project: str | None = None
    repository: str | None = None
    service: str | None = None
    environment: str | None = None

    @property
    def normalized_base_url(self) -> str:
        return str(self.base_url).rstrip("/")

    @property
    def organization_base_url(self) -> str:
        return f"{self.normalized_base_url}/{self.organization}"

    @property
    def has_personal_access_token(self) -> bool:
        return self.personal_access_token is not None
