"""Parse GitHub REST API payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.connectors.github.types import (
    GitHubChangedFile,
    GitHubCommit,
    GitHubDeployment,
    GitHubPullRequest,
    GitHubRelease,
    GitHubRepository,
)


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _login(value: Any) -> str | None:
    if isinstance(value, dict):
        login = value.get("login")
        return str(login) if login is not None else None
    return None


def parse_repository(payload: dict[str, Any]) -> GitHubRepository:
    return GitHubRepository.model_validate(payload)


def parse_repositories(payload: list[Any]) -> list[GitHubRepository]:
    repositories: list[GitHubRepository] = []
    for item in payload:
        if isinstance(item, dict):
            repositories.append(parse_repository(item))
    return repositories


def parse_commit(payload: dict[str, Any]) -> GitHubCommit | None:
    sha = payload.get("sha")
    commit = payload.get("commit")
    if not isinstance(sha, str) or not isinstance(commit, dict):
        return None

    message = commit.get("message")
    if not isinstance(message, str):
        return None

    author_block = commit.get("author")
    committed_at = None
    author = None
    if isinstance(author_block, dict):
        committed_at = _parse_timestamp(author_block.get("date"))
        author = author_block.get("name")
        if author is not None:
            author = str(author)
    if committed_at is None:
        committed_at = _parse_timestamp(commit.get("committer", {}).get("date"))
    if committed_at is None:
        return None

    return GitHubCommit(
        sha=sha,
        message=message,
        author=author,
        committed_at=committed_at,
        html_url=payload.get("html_url"),
    )


def parse_commits(payload: list[Any]) -> list[GitHubCommit]:
    commits: list[GitHubCommit] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        commit = parse_commit(item)
        if commit is not None:
            commits.append(commit)
    return commits


def parse_pull_request(payload: dict[str, Any]) -> GitHubPullRequest | None:
    number = payload.get("number")
    title = payload.get("title")
    state = payload.get("state")
    created_at = _parse_timestamp(payload.get("created_at"))
    if not isinstance(number, int) or not isinstance(title, str):
        return None
    if not isinstance(state, str) or created_at is None:
        return None

    head = payload.get("head")
    head_sha = head.get("sha") if isinstance(head, dict) else None

    return GitHubPullRequest(
        number=number,
        title=title,
        state=state,
        author=_login(payload.get("user")),
        created_at=created_at,
        merged_at=_parse_timestamp(payload.get("merged_at")),
        head_sha=str(head_sha) if head_sha is not None else None,
        html_url=payload.get("html_url"),
    )


def parse_pull_requests(payload: list[Any]) -> list[GitHubPullRequest]:
    pull_requests: list[GitHubPullRequest] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        pull_request = parse_pull_request(item)
        if pull_request is not None:
            pull_requests.append(pull_request)
    return pull_requests


def parse_deployment(payload: dict[str, Any]) -> GitHubDeployment | None:
    deployment_id = payload.get("id")
    sha = payload.get("sha")
    ref = payload.get("ref")
    environment = payload.get("environment")
    created_at = _parse_timestamp(payload.get("created_at"))
    if not isinstance(deployment_id, int):
        return None
    if not isinstance(sha, str) or not isinstance(ref, str):
        return None
    if not isinstance(environment, str) or created_at is None:
        return None

    return GitHubDeployment(
        id=deployment_id,
        sha=sha,
        ref=ref,
        environment=environment,
        author=_login(payload.get("creator")),
        created_at=created_at,
        description=payload.get("description"),
    )


def parse_deployments(payload: list[Any]) -> list[GitHubDeployment]:
    deployments: list[GitHubDeployment] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        deployment = parse_deployment(item)
        if deployment is not None:
            deployments.append(deployment)
    return deployments


def parse_release(payload: dict[str, Any]) -> GitHubRelease | None:
    release_id = payload.get("id")
    tag_name = payload.get("tag_name")
    target_commitish = payload.get("target_commitish")
    if not isinstance(release_id, int):
        return None
    if not isinstance(tag_name, str) or not isinstance(target_commitish, str):
        return None

    return GitHubRelease(
        id=release_id,
        tag_name=tag_name,
        target_commitish=target_commitish,
        author=_login(payload.get("author")),
        published_at=_parse_timestamp(payload.get("published_at")),
        name=payload.get("name"),
        html_url=payload.get("html_url"),
    )


def parse_releases(payload: list[Any]) -> list[GitHubRelease]:
    releases: list[GitHubRelease] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        release = parse_release(item)
        if release is not None:
            releases.append(release)
    return releases


def parse_changed_files(payload: list[Any]) -> list[GitHubChangedFile]:
    files: list[GitHubChangedFile] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if not isinstance(filename, str):
            continue
        files.append(
            GitHubChangedFile(
                filename=filename,
                status=item.get("status"),
                additions=int(item.get("additions", 0)),
                deletions=int(item.get("deletions", 0)),
                changes=int(item.get("changes", 0)),
            )
        )
    return files
