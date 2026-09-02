"""Azure DevOps connector."""

from app.connectors.azure_devops.client import (
    build_auth_headers,
    sanitize_error_message,
)
from app.connectors.azure_devops.config import AzureDevOpsConnectorConfig
from app.connectors.azure_devops.connector import (
    AzureDevOpsConnector,
    create_azure_devops_connector,
)
from app.connectors.azure_devops.convert import (
    azure_build_to_event,
    azure_deployment_to_event,
    azure_release_to_event,
)
from app.connectors.azure_devops.errors import (
    AzureDevOpsAuthenticationError,
    AzureDevOpsError,
    AzureDevOpsNotConnectedError,
    AzureDevOpsQueryError,
    AzureDevOpsTimeoutError,
)
from app.connectors.azure_devops.types import (
    AzureDevOpsBuild,
    AzureDevOpsChangedFile,
    AzureDevOpsCommit,
    AzureDevOpsDeployment,
    AzureDevOpsProject,
    AzureDevOpsRelease,
    AzureDevOpsRepository,
)

__all__ = [
    "AzureDevOpsAuthenticationError",
    "AzureDevOpsBuild",
    "AzureDevOpsChangedFile",
    "AzureDevOpsCommit",
    "AzureDevOpsConnector",
    "AzureDevOpsConnectorConfig",
    "AzureDevOpsDeployment",
    "AzureDevOpsError",
    "AzureDevOpsNotConnectedError",
    "AzureDevOpsProject",
    "AzureDevOpsQueryError",
    "AzureDevOpsRelease",
    "AzureDevOpsRepository",
    "AzureDevOpsTimeoutError",
    "azure_build_to_event",
    "azure_deployment_to_event",
    "azure_release_to_event",
    "build_auth_headers",
    "create_azure_devops_connector",
    "sanitize_error_message",
]
