"""Helpers for splitting and rebuilding connector configuration payloads."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr, ValidationError

from app.connectors.azure_devops import AzureDevOpsConnectorConfig
from app.connectors.database import DatabaseConnectorConfig
from app.connectors.elasticsearch import ElasticsearchConnectorConfig
from app.connectors.github import GitHubConnectorConfig
from app.connectors.opensearch import OpenSearchConnectorConfig
from app.connectors.prometheus import PrometheusConnectorConfig
from app.connectors.types import ConnectorConfig, ConnectorType

SECRET_FIELDS: dict[ConnectorType, frozenset[str]] = {
    ConnectorType.PROMETHEUS: frozenset({"bearer_token", "password"}),
    ConnectorType.OPENSEARCH: frozenset({"bearer_token", "password"}),
    ConnectorType.ELASTICSEARCH: frozenset({"bearer_token", "password"}),
    ConnectorType.GITHUB: frozenset({"token"}),
    ConnectorType.AZURE_DEVOPS: frozenset({"personal_access_token"}),
    ConnectorType.DATABASE: frozenset({"connection_url"}),
}

_CONFIG_MODELS: dict[ConnectorType, type[ConnectorConfig]] = {
    ConnectorType.PROMETHEUS: PrometheusConnectorConfig,
    ConnectorType.OPENSEARCH: OpenSearchConnectorConfig,
    ConnectorType.ELASTICSEARCH: ElasticsearchConnectorConfig,
    ConnectorType.GITHUB: GitHubConnectorConfig,
    ConnectorType.AZURE_DEVOPS: AzureDevOpsConnectorConfig,
    ConnectorType.DATABASE: DatabaseConnectorConfig,
}


class ConnectorConfigError(ValueError):
    """Raised when connector settings or credentials fail validation."""


def secret_fields_for(connector_type: ConnectorType) -> frozenset[str]:
    return SECRET_FIELDS[connector_type]


def split_payload(
    connector_type: ConnectorType,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a flat config payload into public settings and secret credentials."""

    secrets = secret_fields_for(connector_type)
    settings: dict[str, Any] = {}
    credentials: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"connector_type", "name"}:
            continue
        if key in secrets:
            credentials[key] = value
        else:
            settings[key] = value
    return settings, credentials


def merge_credentials(
    existing: dict[str, Any],
    updates: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge credential updates. Omitted keys keep existing; ``None`` clears."""

    if updates is None:
        return dict(existing)
    merged = dict(existing)
    for key, value in updates.items():
        if value is None or value == "":
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def build_connector_config(
    *,
    connector_type: ConnectorType,
    name: str,
    settings: dict[str, Any],
    credentials: dict[str, Any],
) -> ConnectorConfig:
    """Validate and construct a typed connector config for the registry."""

    model = _CONFIG_MODELS[connector_type]
    payload = {
        **settings,
        **credentials,
        "connector_type": connector_type,
        "name": name,
    }
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ConnectorConfigError(str(exc)) from exc


def public_settings(
    settings: dict[str, Any], connector_type: ConnectorType
) -> dict[str, Any]:
    """Return settings with any accidental secret keys removed."""

    secrets = secret_fields_for(connector_type)
    return {key: value for key, value in settings.items() if key not in secrets}


def configured_credential_keys(credentials: dict[str, Any]) -> list[str]:
    return sorted(
        key for key, value in credentials.items() if value is not None and value != ""
    )


def config_to_runtime_dict(config: ConnectorConfig) -> dict[str, Any]:
    """Serialize a connector config, unwrapping ``SecretStr`` values."""

    data = config.model_dump(mode="python")
    for key, value in list(data.items()):
        if isinstance(value, SecretStr):
            data[key] = value.get_secret_value()
    return data
