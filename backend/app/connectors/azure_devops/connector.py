"""Azure DevOps connector implementation."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.connectors.azure_devops.client import (
    AzureDevOpsHTTPClient,
    HttpxAzureDevOpsClient,
)
from app.connectors.azure_devops.config import AzureDevOpsConnectorConfig
from app.connectors.azure_devops.convert import (
    azure_build_to_event,
    azure_deployment_to_event,
    azure_release_to_event,
)
from app.connectors.azure_devops.errors import (
    AzureDevOpsAuthenticationError,
    AzureDevOpsNotConnectedError,
    AzureDevOpsQueryError,
    AzureDevOpsTimeoutError,
)
from app.connectors.azure_devops.parse import (
    parse_builds,
    parse_changed_files,
    parse_commits,
    parse_deployments,
    parse_projects,
    parse_releases,
    parse_repositories,
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
from app.connectors.base import Connector
from app.connectors.errors import ConnectorConnectionError
from app.connectors.types import (
    ConnectionTestResult,
    ConnectorState,
    HealthCheckResult,
)
from app.domain.events import DeploymentEvent


class AzureDevOpsConnector(Connector):
    """Connector for Azure DevOps projects, builds, releases, and changes."""

    def __init__(
        self,
        config: AzureDevOpsConnectorConfig,
        *,
        client: AzureDevOpsHTTPClient | None = None,
    ) -> None:
        super().__init__(config)
        self._azure_config = config
        self._client = client
        self._owns_client = client is None

    @property
    def azure_config(self) -> AzureDevOpsConnectorConfig:
        return self._azure_config

    def _source(self) -> str:
        return f"azure_devops:{self.name}"

    def _project_path(self, project: str) -> str:
        return f"/{quote(project, safe='')}"

    async def connect(self) -> None:
        if self._client is None:
            self._client = HttpxAzureDevOpsClient(self._azure_config)
            self._owns_client = True
        try:
            await self._probe_api(self._client)
            self._state = ConnectorState.CONNECTED
        except (
            AzureDevOpsTimeoutError,
            AzureDevOpsAuthenticationError,
            ConnectorConnectionError,
        ) as exc:
            self._state = ConnectorState.ERROR
            raise ConnectorConnectionError(str(exc)) from exc

    async def disconnect(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._state = ConnectorState.DISCONNECTED

    async def health_check(self) -> HealthCheckResult:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            return HealthCheckResult(
                connector_type=self.connector_type,
                name=self.name,
                healthy=False,
                state=self.state,
                detail="not connected",
            )

        try:
            await self._probe_api(self._client)
            healthy = True
            detail = "ok"
        except (
            AzureDevOpsTimeoutError,
            AzureDevOpsAuthenticationError,
            ConnectorConnectionError,
        ) as exc:
            healthy = False
            detail = str(exc)

        return HealthCheckResult(
            connector_type=self.connector_type,
            name=self.name,
            healthy=healthy,
            state=self.state,
            detail=detail,
        )

    async def test_connection(self) -> ConnectionTestResult:
        probe_client = self._client
        created_probe = False
        if probe_client is None:
            probe_client = HttpxAzureDevOpsClient(self._azure_config)
            created_probe = True

        try:
            await self._probe_api(probe_client)
            success = True
            detail = "ok"
        except (
            AzureDevOpsTimeoutError,
            AzureDevOpsAuthenticationError,
            ConnectorConnectionError,
        ) as exc:
            success = False
            detail = str(exc)
        finally:
            if created_probe:
                await probe_client.aclose()

        return ConnectionTestResult(
            connector_type=self.connector_type,
            name=self.name,
            success=success,
            detail=detail,
        )

    async def list_projects(self, *, top: int = 100) -> list[AzureDevOpsProject]:
        """List projects in the configured organization."""

        client = self._require_client()
        payload = await self._get_json(
            client,
            "/_apis/projects",
            params={"api-version": self._azure_config.api_version, "$top": top},
        )
        return parse_projects(payload)

    async def list_repositories(
        self,
        project: str,
        *,
        top: int = 100,
    ) -> list[AzureDevOpsRepository]:
        """List Git repositories for a project."""

        client = self._require_client()
        path = f"{self._project_path(project)}/_apis/git/repositories"
        payload = await self._get_json(
            client,
            path,
            params={"api-version": self._azure_config.api_version, "$top": top},
        )
        return parse_repositories(payload)

    async def list_builds(
        self,
        project: str,
        *,
        top: int = 50,
        result_filter: str | None = "succeeded",
    ) -> list[AzureDevOpsBuild]:
        """List pipeline builds for a project."""

        client = self._require_client()
        params: dict[str, str | int] = {
            "api-version": self._azure_config.api_version,
            "$top": top,
        }
        if result_filter is not None:
            params["resultFilter"] = result_filter

        path = f"{self._project_path(project)}/_apis/build/builds"
        payload = await self._get_json(client, path, params=params)
        return parse_builds(payload)

    async def list_releases(
        self,
        project: str,
        *,
        top: int = 50,
    ) -> list[AzureDevOpsRelease]:
        """List classic release pipeline releases."""

        client = self._require_client()
        path = f"{self._project_path(project)}/_apis/release/releases"
        payload = await self._get_json(
            client,
            path,
            params={"api-version": self._azure_config.api_version, "$top": top},
        )
        return parse_releases(payload)

    async def list_deployments(
        self,
        project: str,
        *,
        top: int = 50,
    ) -> list[AzureDevOpsDeployment]:
        """List release environment deployments."""

        client = self._require_client()
        path = f"{self._project_path(project)}/_apis/release/deployments"
        payload = await self._get_json(
            client,
            path,
            params={
                "api-version": self._azure_config.api_version,
                "$top": top,
                "deploymentStatus": "succeeded",
            },
        )
        return parse_deployments(payload)

    async def list_commits(
        self,
        project: str,
        repository_id: str,
        *,
        top: int = 50,
    ) -> list[AzureDevOpsCommit]:
        """List commits for a repository."""

        client = self._require_client()
        path = (
            f"{self._project_path(project)}/_apis/git/repositories/"
            f"{quote(repository_id, safe='')}/commits"
        )
        payload = await self._get_json(
            client,
            path,
            params={"api-version": self._azure_config.api_version, "$top": top},
        )
        return parse_commits(payload)

    async def get_commit_changes(
        self,
        project: str,
        repository_id: str,
        commit_id: str,
    ) -> list[AzureDevOpsChangedFile]:
        """Return files changed in a commit."""

        client = self._require_client()
        path = (
            f"{self._project_path(project)}/_apis/git/repositories/"
            f"{quote(repository_id, safe='')}/commits/"
            f"{quote(commit_id, safe='')}/changes"
        )
        payload = await self._get_json(
            client,
            path,
            params={"api-version": self._azure_config.api_version},
        )
        return parse_changed_files(payload)

    async def list_deployment_events(
        self,
        project: str,
        repository_name: str,
        *,
        repository_id: str | None = None,
        include_changed_files: bool = True,
        top: int = 50,
    ) -> list[DeploymentEvent]:
        """Fetch builds, releases, and deployments as deployment events."""

        repository = f"{project}/{repository_name}"
        source = self._source()
        service = self._azure_config.service
        environment = self._azure_config.environment

        events: list[DeploymentEvent] = []
        builds = await self.list_builds(project, top=top)
        for build in builds:
            changed_files: list[str] = []
            if (
                include_changed_files
                and repository_id is not None
                and build.source_version is not None
            ):
                files = await self.get_commit_changes(
                    project,
                    repository_id,
                    build.source_version,
                )
                changed_files = [file.path for file in files]
            event = azure_build_to_event(
                build,
                repository=repository,
                source=source,
                changed_files=changed_files,
                service=service,
                environment=environment,
            )
            if event is not None:
                events.append(event)

        releases = await self.list_releases(project, top=top)
        for release in releases:
            event = azure_release_to_event(
                release,
                repository=repository,
                source=source,
                service=service,
                environment=environment,
            )
            if event is not None:
                events.append(event)

        deployments = await self.list_deployments(project, top=top)
        for deployment in deployments:
            event = azure_deployment_to_event(
                deployment,
                repository=repository,
                source=source,
                service=service,
                environment=environment,
            )
            if event is not None:
                events.append(event)

        events.sort(key=lambda item: item.timestamp)
        return events

    async def _probe_api(self, client: AzureDevOpsHTTPClient) -> None:
        await client.get_json(
            "/_apis/projects",
            params={
                "api-version": self._azure_config.api_version,
                "$top": 1,
            },
        )

    def _require_client(self) -> AzureDevOpsHTTPClient:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            raise AzureDevOpsNotConnectedError(
                "azure devops connector is not connected"
            )
        return self._client

    async def _get_json(
        self,
        client: AzureDevOpsHTTPClient,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any:
        try:
            return await client.get_json(path, params=params)
        except AzureDevOpsTimeoutError:
            raise
        except (AzureDevOpsAuthenticationError, ConnectorConnectionError) as exc:
            raise AzureDevOpsQueryError(str(exc)) from exc


def create_azure_devops_connector(
    config: AzureDevOpsConnectorConfig,
) -> AzureDevOpsConnector:
    """Factory used by :class:`~app.connectors.registry.ConnectorRegistry`."""

    return AzureDevOpsConnector(config)
