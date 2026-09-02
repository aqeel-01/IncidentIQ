"""Mocked integration tests for the GitHub connector."""

from __future__ import annotations

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
from app.connectors.errors import ConnectorConnectionError
from app.connectors.github import (
    GitHubConnector,
    GitHubConnectorConfig,
    GitHubNotConnectedError,
    create_github_connector,
    github_deployment_to_event,
    github_release_to_event,
    sanitize_error_message,
)
from app.connectors.github.client import HttpxGitHubClient, build_auth_headers
from app.connectors.github.parse import (
    parse_commit,
    parse_commits,
    parse_deployment,
    parse_pull_request,
    parse_release,
    parse_repository,
)
from app.connectors.github.types import GitHubRelease
from app.domain.events import DeploymentEvent


def _config(**overrides: object) -> GitHubConnectorConfig:
    base: dict[str, object] = {
        "name": "repo-events",
        "token": SecretStr("ghp_supersecret_token_value"),
        "service": "payments-api",
        "environment": "production",
        "owner": "incidentiq",
        "repository": "payments",
    }
    base.update(overrides)
    return GitHubConnectorConfig(**base)


REPO_PAYLOAD = {
    "id": 1,
    "full_name": "incidentiq/payments",
    "name": "payments",
    "private": False,
    "default_branch": "main",
}

COMMIT_PAYLOAD = {
    "sha": "abc123",
    "html_url": "https://github.com/incidentiq/payments/commit/abc123",
    "commit": {
        "message": "fix checkout timeout",
        "author": {"name": "dev", "date": "2026-09-01T12:00:00Z"},
    },
}

PULL_REQUEST_PAYLOAD = {
    "number": 42,
    "title": "Improve retries",
    "state": "open",
    "created_at": "2026-09-01T11:00:00Z",
    "merged_at": None,
    "user": {"login": "dev"},
    "head": {"sha": "abc123"},
}

DEPLOYMENT_PAYLOAD = {
    "id": 99,
    "sha": "abc123",
    "ref": "v1.2.3",
    "environment": "production",
    "created_at": "2026-09-01T12:30:00Z",
    "creator": {"login": "deploy-bot"},
    "description": "production rollout",
}

RELEASE_PAYLOAD = {
    "id": 7,
    "tag_name": "v1.2.3",
    "target_commitish": "abc123",
    "published_at": "2026-09-01T12:45:00Z",
    "author": {"login": "release-bot"},
    "name": "September release",
}

CHANGED_FILES_PAYLOAD = [
    {
        "filename": "src/payments/checkout.py",
        "status": "modified",
        "additions": 10,
        "deletions": 2,
        "changes": 12,
    },
    {
        "filename": "tests/test_checkout.py",
        "status": "modified",
        "additions": 4,
        "deletions": 0,
        "changes": 4,
    },
]


class MockGitHubHTTPClient:
    """In-memory GitHub HTTP client for connector tests."""

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


def _connected_connector(
  client: MockGitHubHTTPClient,
) -> GitHubConnector:
    return GitHubConnector(_config(), client=client)


@pytest.mark.asyncio
async def test_connect_and_health_check_use_authenticated_user_probe() -> None:
    client = MockGitHubHTTPClient({"/user": {"login": "incidentiq"}})
    connector = GitHubConnector(_config(), client=client)

    await connector.connect()
    health = await connector.health_check()

    assert connector.state is ConnectorState.CONNECTED
    assert health.healthy is True
    assert client.calls[0][0] == "/user"


@pytest.mark.asyncio
async def test_list_repositories_commits_pulls_deployments_releases() -> None:
    client = MockGitHubHTTPClient(
        {
            "/user": {"login": "incidentiq"},
            "/user/repos": [REPO_PAYLOAD],
            "/repos/incidentiq/payments/commits": [COMMIT_PAYLOAD],
            "/repos/incidentiq/payments/pulls": [PULL_REQUEST_PAYLOAD],
            "/repos/incidentiq/payments/deployments": [DEPLOYMENT_PAYLOAD],
            "/repos/incidentiq/payments/releases": [RELEASE_PAYLOAD],
        }
    )
    connector = _connected_connector(client)
    await connector.connect()

    repositories = await connector.list_repositories()
    commits = await connector.list_commits("incidentiq", "payments")
    pull_requests = await connector.list_pull_requests("incidentiq", "payments")
    deployments = await connector.list_deployments("incidentiq", "payments")
    releases = await connector.list_releases("incidentiq", "payments")

    assert repositories[0].full_name == "incidentiq/payments"
    assert commits[0].sha == "abc123"
    assert pull_requests[0].number == 42
    assert deployments[0].ref == "v1.2.3"
    assert releases[0].tag_name == "v1.2.3"


@pytest.mark.asyncio
async def test_changed_files_from_commit_and_pull_request() -> None:
    client = MockGitHubHTTPClient(
        {
            "/user": {"login": "incidentiq"},
            "/repos/incidentiq/payments/commits/abc123": {
                "files": CHANGED_FILES_PAYLOAD,
            },
            "/repos/incidentiq/payments/pulls/42/files": CHANGED_FILES_PAYLOAD,
        }
    )
    connector = _connected_connector(client)
    await connector.connect()

    commit_files = await connector.get_commit_changed_files(
        "incidentiq",
        "payments",
        "abc123",
    )
    pull_request_files = await connector.get_pull_request_changed_files(
        "incidentiq",
        "payments",
        42,
    )

    assert [file.filename for file in commit_files] == [
        "src/payments/checkout.py",
        "tests/test_checkout.py",
    ]
    assert [file.filename for file in pull_request_files] == [
        "src/payments/checkout.py",
        "tests/test_checkout.py",
    ]


def test_deployment_and_release_convert_to_deployment_event() -> None:
    deployment = parse_deployment(DEPLOYMENT_PAYLOAD)
    release = parse_release(RELEASE_PAYLOAD)
    assert deployment is not None
    assert release is not None

    deployment_event = github_deployment_to_event(
        deployment,
        repository="incidentiq/payments",
        source="github:repo-events",
        changed_files=["src/payments/checkout.py"],
        service="payments-api",
        environment="production",
    )
    release_event = github_release_to_event(
        release,
        repository="incidentiq/payments",
        source="github:repo-events",
        changed_files=["src/payments/checkout.py"],
        service="payments-api",
        environment="production",
    )

    assert isinstance(deployment_event, DeploymentEvent)
    assert deployment_event.version == "v1.2.3"
    assert deployment_event.commit_sha == "abc123"
    assert deployment_event.author == "deploy-bot"
    assert deployment_event.changed_files == ["src/payments/checkout.py"]

    assert release_event is not None
    assert release_event.version == "v1.2.3"
    assert release_event.commit_sha == "abc123"
    assert release_event.author == "release-bot"


@pytest.mark.asyncio
async def test_list_deployment_events_includes_changed_files() -> None:
    client = MockGitHubHTTPClient(
        {
            "/user": {"login": "incidentiq"},
            "/repos/incidentiq/payments/deployments": [DEPLOYMENT_PAYLOAD],
            "/repos/incidentiq/payments/releases": [RELEASE_PAYLOAD],
            "/repos/incidentiq/payments/commits/abc123": {
                "files": CHANGED_FILES_PAYLOAD,
            },
        }
    )
    connector = _connected_connector(client)
    await connector.connect()

    events = await connector.list_deployment_events("incidentiq", "payments")

    assert len(events) == 2
    assert all(isinstance(event, DeploymentEvent) for event in events)
    assert events[0].changed_files == [
        "src/payments/checkout.py",
        "tests/test_checkout.py",
    ]
    assert events[1].changed_files == [
        "src/payments/checkout.py",
        "tests/test_checkout.py",
    ]


@pytest.mark.asyncio
async def test_search_without_connect_raises_not_connected() -> None:
    connector = GitHubConnector(_config())

    with pytest.raises(GitHubNotConnectedError):
        await connector.list_repositories()


def test_sanitize_error_message_redacts_tokens() -> None:
    message = (
        "github request failed: Authorization token ghp_supersecret_token_value invalid"
    )

    sanitized = sanitize_error_message(message)

    assert "ghp_supersecret_token_value" not in sanitized
    assert "***" in sanitized


def test_config_repr_does_not_expose_token() -> None:
    config = _config()

    rendered = repr(config)

    assert "ghp_supersecret_token_value" not in rendered


def test_build_auth_headers_supports_bearer_and_token_schemes() -> None:
    bearer_headers = build_auth_headers(_config(auth_scheme="bearer"))
    token_headers = build_auth_headers(_config(auth_scheme="token"))

    assert bearer_headers["Authorization"].startswith("Bearer ")
    assert token_headers["Authorization"].startswith("token ")


@pytest.mark.asyncio
async def test_httpx_client_applies_bearer_authentication(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def get(self, path: str, **kwargs: object):
            request = httpx.Request("GET", f"https://api.github.com{path}")
            return httpx.Response(200, json={"login": "incidentiq"}, request=request)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.connectors.github.client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    client = HttpxGitHubClient(_config())
    await client.get_json("/user")
    await client.aclose()

    headers = captured["headers"]
    assert headers["Authorization"].startswith("Bearer ")


def test_registry_creates_github_connector() -> None:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.GITHUB, create_github_connector)

    connector = registry.create(_config())

    assert isinstance(connector, GitHubConnector)


def test_default_registry_includes_github_connector() -> None:
    registry = default_connector_registry()
    connector = registry.create(_config())

    assert isinstance(connector, GitHubConnector)


def test_parse_helpers_handle_valid_and_invalid_payloads() -> None:
    repository = parse_repository(REPO_PAYLOAD)
    commit = parse_commit(COMMIT_PAYLOAD)
    pull_request = parse_pull_request(PULL_REQUEST_PAYLOAD)
    commits = parse_commits([COMMIT_PAYLOAD, {"sha": "bad"}])

    assert repository.full_name == "incidentiq/payments"
    assert commit is not None
    assert commit.message == "fix checkout timeout"
    assert pull_request is not None
    assert pull_request.number == 42
    assert len(commits) == 1


def test_release_without_publish_date_is_skipped_in_conversion() -> None:
    release = GitHubRelease(
        id=1,
        tag_name="v0.0.1",
        target_commitish="abc",
        published_at=None,
    )

    event = github_release_to_event(
        release,
        repository="incidentiq/payments",
        source="github:repo-events",
    )

    assert event is None
