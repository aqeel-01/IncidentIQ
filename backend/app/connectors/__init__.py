"""External source connector abstractions.

Connectors are isolated from the investigation engine. Concrete provider
implementations (OpenSearch, Prometheus, GitHub, etc.) plug into this layer
and expose a uniform lifecycle API.
"""

from app.connectors.azure_devops import (
    AzureDevOpsConnector,
    AzureDevOpsConnectorConfig,
    create_azure_devops_connector,
)
from app.connectors.base import Connector
from app.connectors.database import (
    DatabaseConnector,
    DatabaseConnectorConfig,
    create_database_connector,
)
from app.connectors.elasticsearch import (
    ElasticsearchConnector,
    ElasticsearchConnectorConfig,
    create_elasticsearch_connector,
)
from app.connectors.errors import (
    ConnectorConnectionError,
    ConnectorError,
    ConnectorNotConnectedError,
    ConnectorRegistrationError,
)
from app.connectors.github import (
    GitHubConnector,
    GitHubConnectorConfig,
    create_github_connector,
)
from app.connectors.opensearch import (
    OpenSearchConnector,
    OpenSearchConnectorConfig,
    create_opensearch_connector,
)
from app.connectors.prometheus import (
    PrometheusConnector,
    PrometheusConnectorConfig,
    create_prometheus_connector,
)
from app.connectors.registry import ConnectorFactory, ConnectorRegistry
from app.connectors.types import (
    ConnectionTestResult,
    ConnectorConfig,
    ConnectorState,
    ConnectorType,
    HealthCheckResult,
)

__all__ = [
    "AzureDevOpsConnector",
    "AzureDevOpsConnectorConfig",
    "ConnectionTestResult",
    "Connector",
    "ConnectorConfig",
    "ConnectorConnectionError",
    "ConnectorError",
    "ConnectorFactory",
    "ConnectorNotConnectedError",
    "ConnectorRegistrationError",
    "ConnectorRegistry",
    "ConnectorState",
    "ConnectorType",
    "DatabaseConnector",
    "DatabaseConnectorConfig",
    "ElasticsearchConnector",
    "ElasticsearchConnectorConfig",
    "GitHubConnector",
    "GitHubConnectorConfig",
    "HealthCheckResult",
    "OpenSearchConnector",
    "OpenSearchConnectorConfig",
    "PrometheusConnector",
    "PrometheusConnectorConfig",
    "create_azure_devops_connector",
    "create_database_connector",
    "create_elasticsearch_connector",
    "create_github_connector",
    "create_opensearch_connector",
    "create_prometheus_connector",
    "default_connector_registry",
]


def default_connector_registry() -> ConnectorRegistry:
    """Return a registry with built-in connector implementations registered."""

    def _opensearch_factory(config: ConnectorConfig) -> Connector:
        if not isinstance(config, OpenSearchConnectorConfig):
            msg = "opensearch factory requires OpenSearchConnectorConfig"
            raise ConnectorRegistrationError(msg)
        return create_opensearch_connector(config)

    def _database_factory(config: ConnectorConfig) -> Connector:
        if not isinstance(config, DatabaseConnectorConfig):
            msg = "database factory requires DatabaseConnectorConfig"
            raise ConnectorRegistrationError(msg)
        return create_database_connector(config)

    def _elasticsearch_factory(config: ConnectorConfig) -> Connector:
        if not isinstance(config, ElasticsearchConnectorConfig):
            msg = "elasticsearch factory requires ElasticsearchConnectorConfig"
            raise ConnectorRegistrationError(msg)
        return create_elasticsearch_connector(config)

    def _github_factory(config: ConnectorConfig) -> Connector:
        if not isinstance(config, GitHubConnectorConfig):
            msg = "github factory requires GitHubConnectorConfig"
            raise ConnectorRegistrationError(msg)
        return create_github_connector(config)

    def _azure_devops_factory(config: ConnectorConfig) -> Connector:
        if not isinstance(config, AzureDevOpsConnectorConfig):
            msg = "azure devops factory requires AzureDevOpsConnectorConfig"
            raise ConnectorRegistrationError(msg)
        return create_azure_devops_connector(config)

    def _prometheus_factory(config: ConnectorConfig) -> Connector:
        if not isinstance(config, PrometheusConnectorConfig):
            msg = "prometheus factory requires PrometheusConnectorConfig"
            raise ConnectorRegistrationError(msg)
        return create_prometheus_connector(config)

    registry = ConnectorRegistry()
    registry.register(ConnectorType.OPENSEARCH, _opensearch_factory)
    registry.register(ConnectorType.DATABASE, _database_factory)
    registry.register(ConnectorType.ELASTICSEARCH, _elasticsearch_factory)
    registry.register(ConnectorType.GITHUB, _github_factory)
    registry.register(ConnectorType.AZURE_DEVOPS, _azure_devops_factory)
    registry.register(ConnectorType.PROMETHEUS, _prometheus_factory)
    return registry
