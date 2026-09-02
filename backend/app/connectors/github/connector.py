"""GitHub connector implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from app.connectors.base import Connector
from app.connectors.errors import ConnectorConnectionError
from app.connectors.github.client import GitHubHTTPClient, HttpxGitHubClient
from app.connectors.github.config import GitHubConnectorConfig
from app.connectors.github.convert import (
    github_deployment_to_event,
    github_release_to_event,
)
from app.connectors.github.errors import (
    GitHubAuthenticationError,
    GitHubNotConnectedError,
    GitHubQueryError,
    GitHubTimeoutError,
)
from app.connectors.github.parse import (
    parse_changed_files,
    parse_commits,
    parse_deployments,
    parse_pull_requests,
    parse_releases,
    parse_repositories,
)
from app.connectors.github.types import (
    GitHubChangedFile,
    GitHubCommit,
    GitHubDeployment,
    GitHubPullRequest,
    GitHubRelease,
    GitHubRepository,
)
from app.connectors.types import (
    ConnectionTestResult,
    ConnectorState,
    HealthCheckResult,
)
from app.domain.events import DeploymentEvent


class GitHubConnector(Connector):
    """Connector for GitHub repositories, changes, and deployments."""

    def __init__(
        self,
        config: GitHubConnectorConfig,
        *,
        client: GitHubHTTPClient | None = None,
    ) -> None:
        super().__init__(config)
        self._github_config = config
        self._client = client
        self._owns_client = client is None

    @property
    def github_config(self) -> GitHubConnectorConfig:
        return self._github_config

    def _source(self) -> str:
        return f"github:{self.name}"

    def _repository_path(self, owner: str, repo: str) -> str:
        return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    async def connect(self) -> None:
        if self._client is None:
            self._client = HttpxGitHubClient(self._github_config)
            self._owns_client = True
        try:
            await self._probe_api(self._client)
            self._state = ConnectorState.CONNECTED
        except (
            GitHubTimeoutError,
            GitHubAuthenticationError,
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
            GitHubTimeoutError,
            GitHubAuthenticationError,
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
            probe_client = HttpxGitHubClient(self._github_config)
            created_probe = True

        try:
            await self._probe_api(probe_client)
            success = True
            detail = "ok"
        except (
            GitHubTimeoutError,
            GitHubAuthenticationError,
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

    async def list_repositories(
        self,
        *,
        org: str | None = None,
        per_page: int = 30,
    ) -> list[GitHubRepository]:
        """List repositories for the authenticated user or an organization."""

        client = self._require_client()
        if org is not None:
            path = f"/orgs/{quote(org, safe='')}/repos"
        else:
            path = "/user/repos"
        payload = await self._get_list(client, path, per_page=per_page)
        return parse_repositories(payload)

    async def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        sha: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        per_page: int = 30,
    ) -> list[GitHubCommit]:
        """List commits for a repository."""

        client = self._require_client()
        params: dict[str, str | int] = {"per_page": per_page}
        if sha is not None:
            params["sha"] = sha
        if since is not None:
            params["since"] = since.astimezone(UTC).isoformat()
        if until is not None:
            params["until"] = until.astimezone(UTC).isoformat()

        path = f"{self._repository_path(owner, repo)}/commits"
        payload = await self._get_list(client, path, params=params)
        return parse_commits(payload)

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        per_page: int = 30,
    ) -> list[GitHubPullRequest]:
        """List pull requests for a repository."""

        client = self._require_client()
        path = f"{self._repository_path(owner, repo)}/pulls"
        payload = await self._get_list(
            client,
            path,
            params={"state": state, "per_page": per_page},
        )
        return parse_pull_requests(payload)

    async def list_deployments(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 30,
    ) -> list[GitHubDeployment]:
        """List deployments for a repository."""

        client = self._require_client()
        path = f"{self._repository_path(owner, repo)}/deployments"
        payload = await self._get_list(client, path, per_page=per_page)
        return parse_deployments(payload)

    async def list_releases(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 30,
    ) -> list[GitHubRelease]:
        """List releases for a repository."""

        client = self._require_client()
        path = f"{self._repository_path(owner, repo)}/releases"
        payload = await self._get_list(client, path, per_page=per_page)
        return parse_releases(payload)

    async def get_commit_changed_files(
        self,
        owner: str,
        repo: str,
        sha: str,
    ) -> list[GitHubChangedFile]:
        """Return files changed in a commit."""

        client = self._require_client()
        path = f"{self._repository_path(owner, repo)}/commits/{quote(sha, safe='')}"
        payload = await self._get_json(client, path)
        if not isinstance(payload, dict):
            return []
        files = payload.get("files", [])
        if not isinstance(files, list):
            return []
        return parse_changed_files(files)

    async def get_pull_request_changed_files(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> list[GitHubChangedFile]:
        """Return files changed in a pull request."""

        client = self._require_client()
        path = (
            f"{self._repository_path(owner, repo)}/pulls/{pull_number}/files"
        )
        payload = await self._get_list(client, path)
        return parse_changed_files(payload)

    async def list_deployment_events(
        self,
        owner: str,
        repo: str,
        *,
        include_changed_files: bool = True,
        per_page: int = 30,
    ) -> list[DeploymentEvent]:
        """Fetch deployments and releases and convert them to deployment events."""

        repository = f"{owner}/{repo}"
        source = self._source()
        service = self._github_config.service
        environment = self._github_config.environment

        events: list[DeploymentEvent] = []
        deployments = await self.list_deployments(owner, repo, per_page=per_page)
        for deployment in deployments:
            changed_files: list[str] = []
            if include_changed_files:
                files = await self.get_commit_changed_files(
                    owner,
                    repo,
                    deployment.sha,
                )
                changed_files = [file.filename for file in files]
            events.append(
                github_deployment_to_event(
                    deployment,
                    repository=repository,
                    source=source,
                    changed_files=changed_files,
                    service=service,
                    environment=environment,
                )
            )

        releases = await self.list_releases(owner, repo, per_page=per_page)
        for release in releases:
            changed_files = []
            if include_changed_files:
                files = await self.get_commit_changed_files(
                    owner,
                    repo,
                    release.target_commitish,
                )
                changed_files = [file.filename for file in files]
            event = github_release_to_event(
                release,
                repository=repository,
                source=source,
                changed_files=changed_files,
                service=service,
                environment=environment,
            )
            if event is not None:
                events.append(event)

        events.sort(key=lambda item: item.timestamp)
        return events

    async def _probe_api(self, client: GitHubHTTPClient) -> None:
        if self._github_config.has_token:
            await client.get_json("/user")
        else:
            await client.get_json("/zen")

    def _require_client(self) -> GitHubHTTPClient:
        if self._client is None or self.state is not ConnectorState.CONNECTED:
            raise GitHubNotConnectedError("github connector is not connected")
        return self._client

    async def _get_json(
        self,
        client: GitHubHTTPClient,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any:
        try:
            return await client.get_json(path, params=params)
        except GitHubTimeoutError:
            raise
        except (GitHubAuthenticationError, ConnectorConnectionError) as exc:
            raise GitHubQueryError(str(exc)) from exc

    async def _get_list(
        self,
        client: GitHubHTTPClient,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        per_page: int | None = None,
    ) -> list[Any]:
        request_params = dict(params or {})
        if per_page is not None:
            request_params["per_page"] = per_page
        payload = await self._get_json(client, path, params=request_params)
        if not isinstance(payload, list):
            msg = f"github response for {path} must be a JSON array"
            raise GitHubQueryError(msg)
        return payload


def create_github_connector(config: GitHubConnectorConfig) -> GitHubConnector:
    """Factory used by :class:`~app.connectors.registry.ConnectorRegistry`."""

    return GitHubConnector(config)
