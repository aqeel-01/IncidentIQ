"""Shared configuration for Elasticsearch-compatible search connectors."""

from __future__ import annotations

from pydantic import Field, HttpUrl, model_validator

from app.connectors.types import ConnectorConfig


class SearchIndexConnectorConfig(ConnectorConfig):
    """Common settings for OpenSearch and Elasticsearch log connectors."""

    base_url: HttpUrl | str = Field(min_length=1)
    index: str = Field(min_length=1, description="Target index or index pattern")
    timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    bearer_token: str | None = None
    username: str | None = None
    password: str | None = None
    verify_tls: bool = True
    timestamp_field: str = "@timestamp"
    message_field: str = "message"
    service_field: str = "service"
    environment_field: str = "environment"
    severity_field: str = "severity"
    host_field: str = "host"
    request_id_field: str = "request_id"
    trace_id_field: str = "trace_id"
    default_service: str | None = None
    default_environment: str | None = None

    @model_validator(mode="after")
    def _validate_auth(self) -> SearchIndexConnectorConfig:
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
