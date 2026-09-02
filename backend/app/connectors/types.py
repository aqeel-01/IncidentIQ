"""Shared connector types and result models."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ConnectorType(enum.StrEnum):
    """Supported external data-source connector families."""

    OPENSEARCH = "opensearch"
    ELASTICSEARCH = "elasticsearch"
    DATABASE = "database"
    PROMETHEUS = "prometheus"
    GITHUB = "github"
    AZURE_DEVOPS = "azure_devops"


class ConnectorState(enum.StrEnum):
    """Lifecycle state of a connector instance."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectorConfig(BaseModel):
    """Base configuration shared by every connector implementation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector_type: ConnectorType
    name: str = Field(min_length=1, max_length=255)


class HealthCheckResult(BaseModel):
    """Outcome of a connector ``health_check`` against an active session."""

    model_config = ConfigDict(frozen=True)

    connector_type: ConnectorType
    name: str
    healthy: bool
    state: ConnectorState
    detail: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConnectionTestResult(BaseModel):
    """Outcome of a one-off ``test_connection`` probe."""

    model_config = ConfigDict(frozen=True)

    connector_type: ConnectorType
    name: str
    success: bool
    detail: str
    tested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
