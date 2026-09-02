"""GitHub connector configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, model_validator

from app.connectors.types import ConnectorConfig, ConnectorType


class GitHubConnectorConfig(ConnectorConfig):
    """Configuration for a GitHub connector."""

    connector_type: Literal[ConnectorType.GITHUB] = ConnectorType.GITHUB
    base_url: HttpUrl | str = Field(default="https://api.github.com")
    timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    token: SecretStr | None = None
    auth_scheme: Literal["bearer", "token"] = "bearer"
    verify_tls: bool = True
    owner: str | None = None
    repository: str | None = None
    service: str | None = None
    environment: str | None = None

    @model_validator(mode="after")
    def _validate_auth_scheme(self) -> GitHubConnectorConfig:
        if self.token is None:
            return self
        if self.auth_scheme not in {"bearer", "token"}:
            msg = "auth_scheme must be 'bearer' or 'token'"
            raise ValueError(msg)
        return self

    @property
    def normalized_base_url(self) -> str:
        return str(self.base_url).rstrip("/")

    @property
    def has_token(self) -> bool:
        return self.token is not None
