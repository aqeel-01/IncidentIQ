"""Prometheus connector configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.connectors.types import ConnectorConfig, ConnectorType


class PrometheusConnectorConfig(ConnectorConfig):
    """Configuration for a Prometheus metrics connector."""

    connector_type: Literal[ConnectorType.PROMETHEUS] = ConnectorType.PROMETHEUS
    base_url: HttpUrl | str = Field(min_length=1)
    timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    bearer_token: str | None = None
    username: str | None = None
    password: str | None = None
    verify_tls: bool = True
    service: str | None = None
    environment: str | None = None

    @model_validator(mode="after")
    def _validate_auth(self) -> PrometheusConnectorConfig:
        if self.bearer_token and (self.username or self.password):
            msg = "use either bearer_token or basic auth credentials, not both"
            raise ValueError(msg)
        if (self.username is None) ^ (self.password is None):
            msg = "username and password must both be set for basic auth"
            raise ValueError(msg)
        return self

    @property
    def normalized_base_url(self) -> str:
        return str(self.base_url).rstrip("/")
