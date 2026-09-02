"""Mocked integration tests for the Azure DevOps connector."""

from __future__ import annotations

import base64
import inspect
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.connectors import (
    ConnectorRegistry,
    ConnectorState,
    ConnectorType,
    default_connector_registry,
)
from app.connectors.azure_devops import (
    AzureDevOpsConnector,
    AzureDevOpsConnectorConfig,
    AzureDevOpsNotConnectedError,
    azure_build_to_event,
    azure_deployment_to_event,
    azure_release_to_event,
    create_azure_devops_connector,
    sanitize_error_message,
)
from app.connectors.azure_devops.client import (
    HttpxAzureDevOpsClient,
    build_auth_headers,
)
from app.connectors.azure_devops.parse import (
    parse_build,
    parse_changed_files,
    parse_commit,
    parse_deployment,
    parse_project,
    parse_release,
    parse_repository,
)
from app.connectors.azure_devops.types import AzureDevOpsBuild, AzureDevOpsRelease
from app.connectors.errors import ConnectorConnectionError
from app.domain.events import DeploymentEvent


def _config(**overrides: object) -> AzureDevOpsConnectorConfig:
    base: dict[str, object] = {
        "name": "pipelines",
        "organization": "incidentiq",
        "personal_access_token": SecretStr("azuredevops_supersecret_pat_value"),
        "service": "payments-api",
        "environment": "production",
        "project": "Payments",
        "repository": "payments-api",
    }
    base.update(overrides)
    return AzureDevOpsConnectorConfig(**base)


PROJECT_PAYLOAD = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Payments",
    "description": "Payments platform",
    "state": "wellFormed",
}

REPOSITORY_PAYLOAD = {
    "id": "22222222-2222-2222-2222-222222222222",
    "name": "payments-api",
    "defaultBranch": "refs/heads/main",
    "remoteUrl": "https://dev.azure.com/incidentiq/Payments/_git/payments-api",
    "webUrl": "https://dev.azure.com/incidentiq/Payments/_git/payments-api",
    "project": {"name": "Payments"},
}

BUILD_PAYLOAD = {
    "id": 501,
    "buildNumber": "20260901.1",
    "status": "completed",
    "result": "succeeded",
    "sourceVersion": "abc123def456",
    "queueTime": "2026-09-01T12:00:00Z",
    "finishTime": "2026-09-01T12:30:00Z",
    "requestedBy": {"displayName": "Build Service"},
    "repository": {"name": "payments-api"},
}

RELEASE_PAYLOAD = {
    "id": 88,
    "name": "Release-12",
    "status": "active",
    "createdOn": "2026-09-01T12:45:00Z",
    "createdBy": {"displayName": "Release Manager"},
    "releaseDefinition": {"name": "payments-release"},
}

DEPLOYMENT_PAYLOAD = {
    "id": 301,
    "deploymentStatus": "succeeded",
    "startedOn": "2026-09-01T12:50:00Z",
    "completedOn": "2026-09-01T12:55:00Z",
    "requestedFor": {"displayName": "Deploy Bot"},
    "release": {"id": 88, "name": "Release-12"},
    "releaseEnvironment": {"name": "production"},
}

COMMIT_PAYLOAD = {
    "commitId": "abc123def456",
    "comment": "fix checkout timeout",
    "author": {"name": "dev", "date": "2026-09-01T11:30:00Z"},
    "url": "https://dev.azure.com/incidentiq/Payments/_git/payments-api/commit/abc123",
}

CHANGED_FILES_PAYLOAD = {
    "changeCounts": {"Edit": 2},
    "changes": [
        {"item": {"path": "/src/payments/checkout.py"}, "changeType": "edit"},
        {"item": {"path": "/tests/test_checkout.py"}, "changeType": "edit"},
    ],
}


class MockAzureDevOpsHTTPClient:
    """In-memory Azure DevOps HTTP client for connector tests."""

    def __init__(
        self,
        handlers: dict[str, Callable[[dict[str, str | int] | None], Any]]
        | dict[str, Any]
        | None = None,
    ) -> None:
        self._handlers = handlers or {}
        self.calls: list[tuple[str, dict[str, str | int] | None]] = []

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any:
        self.calls.append((path, params))
        handler = self._handlers.get(path)
        if handler is None:
            msg = f"no mock response for {path}"
            raise ConnectorConnectionError(msg)
        if callable(handler):
            result = handler(params)
            if inspect.isawaitable(result):
                return await result
            return result
        return handler

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_connect_and_health_check_probe_projects() -> None:
    client = MockAzureDevOpsHTTPClient(
        {"/_apis/projects": {"count": 1, "value": [PROJECT_PAYLOAD]}},
    )
    connector = AzureDevOpsConnector(_config(), client=client)

    await connector.connect()
    health = await connector.health_check()

    assert connector.state is ConnectorState.CONNECTED
    assert health.healthy is True
    assert client.calls[0][0] == "/_apis/projects"


@pytest.mark.asyncio
async def test_list_projects_repositories_builds_releases_and_deployments() -> None:
    client = MockAzureDevOpsHTTPClient(
        {
            "/_apis/projects": {"count": 1, "value": [PROJECT_PAYLOAD]},
            "/Payments/_apis/git/repositories": {
                "count": 1,
                "value": [REPOSITORY_PAYLOAD],
            },
            "/Payments/_apis/build/builds": {"count": 1, "value": [BUILD_PAYLOAD]},
            "/Payments/_apis/release/releases": {
                "count": 1,
                "value": [RELEASE_PAYLOAD],
            },
            "/Payments/_apis/release/deployments": {
                "count": 1,
                "value": [DEPLOYMENT_PAYLOAD],
            },
        }
    )
    connector = AzureDevOpsConnector(_config(), client=client)
    await connector.connect()

    projects = await connector.list_projects()
    repositories = await connector.list_repositories("Payments")
    builds = await connector.list_builds("Payments")
    releases = await connector.list_releases("Payments")
    deployments = await connector.list_deployments("Payments")

    assert projects[0].name == "Payments"
    assert repositories[0].name == "payments-api"
    assert builds[0].build_number == "20260901.1"
    assert releases[0].name == "Release-12"
    assert deployments[0].environment_name == "production"


@pytest.mark.asyncio
async def test_list_commits_and_commit_changes() -> None:
    client = MockAzureDevOpsHTTPClient(
        {
            "/_apis/projects": {"count": 1, "value": [PROJECT_PAYLOAD]},
            "/Payments/_apis/git/repositories/"
            "22222222-2222-2222-2222-222222222222/commits": {
                "count": 1,
                "value": [COMMIT_PAYLOAD],
            },
            "/Payments/_apis/git/repositories/"
            "22222222-2222-2222-2222-222222222222/commits/abc123def456/changes": (
                CHANGED_FILES_PAYLOAD
            ),
        }
    )
    connector = AzureDevOpsConnector(_config(), client=client)
    await connector.connect()

    commits = await connector.list_commits(
        "Payments",
        "22222222-2222-2222-2222-222222222222",
    )
    changes = await connector.get_commit_changes(
        "Payments",
        "22222222-2222-2222-2222-222222222222",
        "abc123def456",
    )

    assert commits[0].commit_id == "abc123def456"
    assert [change.path for change in changes] == [
        "/src/payments/checkout.py",
        "/tests/test_checkout.py",
    ]


def test_build_release_and_deployment_convert_to_deployment_event() -> None:
    build = parse_build(BUILD_PAYLOAD)
    release = parse_release(RELEASE_PAYLOAD)
    deployment = parse_deployment(DEPLOYMENT_PAYLOAD)
    assert build is not None
    assert release is not None
    assert deployment is not None

    build_event = azure_build_to_event(
        build,
        repository="Payments/payments-api",
        source="azure_devops:pipelines",
        changed_files=["/src/payments/checkout.py"],
        service="payments-api",
        environment="production",
    )
    release_event = azure_release_to_event(
        release,
        repository="Payments/payments-api",
        source="azure_devops:pipelines",
        service="payments-api",
        environment="production",
    )
    deployment_event = azure_deployment_to_event(
        deployment,
        repository="Payments/payments-api",
        source="azure_devops:pipelines",
        service="payments-api",
        environment="production",
    )

    assert isinstance(build_event, DeploymentEvent)
    assert build_event.version == "20260901.1"
    assert build_event.commit_sha == "abc123def456"
    assert build_event.author == "Build Service"

    assert release_event is not None
    assert release_event.version == "Release-12"
    assert release_event.author == "Release Manager"

    assert deployment_event is not None
    assert deployment_event.environment == "production"
    assert deployment_event.version == "Release-12"


@pytest.mark.asyncio
async def test_list_deployment_events_includes_changed_files() -> None:
    repo_id = "22222222-2222-2222-2222-222222222222"
    client = MockAzureDevOpsHTTPClient(
        {
            "/_apis/projects": {"count": 1, "value": [PROJECT_PAYLOAD]},
            "/Payments/_apis/build/builds": {"count": 1, "value": [BUILD_PAYLOAD]},
            "/Payments/_apis/release/releases": {
                "count": 1,
                "value": [RELEASE_PAYLOAD],
            },
            "/Payments/_apis/release/deployments": {
                "count": 1,
                "value": [DEPLOYMENT_PAYLOAD],
            },
            f"/Payments/_apis/git/repositories/{repo_id}/commits/"
            "abc123def456/changes": CHANGED_FILES_PAYLOAD,
        }
    )
    connector = AzureDevOpsConnector(_config(), client=client)
    await connector.connect()

    events = await connector.list_deployment_events(
        "Payments",
        "payments-api",
        repository_id=repo_id,
    )

    assert len(events) == 3
    assert all(isinstance(event, DeploymentEvent) for event in events)
    assert events[0].changed_files == [
        "/src/payments/checkout.py",
        "/tests/test_checkout.py",
    ]


@pytest.mark.asyncio
async def test_list_projects_without_connect_raises_not_connected() -> None:
    connector = AzureDevOpsConnector(_config())

    with pytest.raises(AzureDevOpsNotConnectedError):
        await connector.list_projects()


def test_sanitize_error_message_redacts_credentials() -> None:
    encoded = base64.b64encode(b":azuredevops_supersecret_pat_value").decode()
    message = f"azure devops request failed: Basic {encoded}"

    sanitized = sanitize_error_message(message)

    assert encoded not in sanitized
    assert "***" in sanitized


def test_config_repr_does_not_expose_personal_access_token() -> None:
    config = _config()

    rendered = repr(config)

    assert "azuredevops_supersecret_pat_value" not in rendered


def test_build_auth_headers_uses_basic_pat_authentication() -> None:
    headers = build_auth_headers(_config())

    assert headers["Authorization"].startswith("Basic ")
    decoded = base64.b64decode(headers["Authorization"].removeprefix("Basic ")).decode()
    assert decoded.endswith("azuredevops_supersecret_pat_value")
    assert decoded.startswith(":")


@pytest.mark.asyncio
async def test_httpx_client_applies_basic_authentication(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def get(self, path: str, **kwargs: object):
            request = httpx.Request(
                "GET",
                f"https://dev.azure.com/incidentiq{path}",
            )
            return httpx.Response(
                200,
                json={"count": 1, "value": [PROJECT_PAYLOAD]},
                request=request,
            )

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.connectors.azure_devops.client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    client = HttpxAzureDevOpsClient(_config())
    await client.get_json("/_apis/projects", params={"api-version": "7.1"})
    await client.aclose()

    headers = captured["headers"]
    assert headers["Authorization"].startswith("Basic ")


def test_registry_creates_azure_devops_connector() -> None:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.AZURE_DEVOPS, create_azure_devops_connector)

    connector = registry.create(_config())

    assert isinstance(connector, AzureDevOpsConnector)


def test_default_registry_includes_azure_devops_connector() -> None:
    registry = default_connector_registry()
    connector = registry.create(_config())

    assert isinstance(connector, AzureDevOpsConnector)


def test_parse_helpers_handle_valid_and_invalid_payloads() -> None:
    project = parse_project(PROJECT_PAYLOAD)
    repository = parse_repository(REPOSITORY_PAYLOAD)
    commit = parse_commit(COMMIT_PAYLOAD)
    changed_files = parse_changed_files(CHANGED_FILES_PAYLOAD)

    assert project is not None
    assert project.name == "Payments"
    assert repository is not None
    assert repository.name == "payments-api"
    assert commit is not None
    assert commit.message == "fix checkout timeout"
    assert [file.path for file in changed_files] == [
        "/src/payments/checkout.py",
        "/tests/test_checkout.py",
    ]


def test_failed_build_is_skipped_in_conversion() -> None:
    build = AzureDevOpsBuild(
        id=1,
        build_number="20260901.2",
        result="failed",
        finish_time=None,
    )

    event = azure_build_to_event(
        build,
        repository="Payments/payments-api",
        source="azure_devops:pipelines",
    )

    assert event is None


def test_release_without_created_on_is_skipped_in_conversion() -> None:
    release = AzureDevOpsRelease(id=1, name="Release-1", created_on=None)

    event = azure_release_to_event(
        release,
        repository="Payments/payments-api",
        source="azure_devops:pipelines",
    )

    assert event is None
