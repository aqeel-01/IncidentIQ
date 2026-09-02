"""Parse Azure DevOps REST API payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.connectors.azure_devops.types import (
    AzureDevOpsBuild,
    AzureDevOpsChangedFile,
    AzureDevOpsCommit,
    AzureDevOpsDeployment,
    AzureDevOpsProject,
    AzureDevOpsRelease,
    AzureDevOpsRepository,
)


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _display_name(value: Any) -> str | None:
    if isinstance(value, dict):
        display_name = value.get("displayName") or value.get("uniqueName")
        return str(display_name) if display_name is not None else None
    return None


def unwrap_value(payload: Any) -> list[Any]:
    """Extract list items from Azure DevOps collection responses."""

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        value = payload.get("value")
        if isinstance(value, list):
            return value
    return []


def parse_project(payload: dict[str, Any]) -> AzureDevOpsProject | None:
    project_id = payload.get("id")
    name = payload.get("name")
    if not isinstance(project_id, str) or not isinstance(name, str):
        return None
    return AzureDevOpsProject(
        id=project_id,
        name=name,
        description=payload.get("description"),
        state=payload.get("state"),
        url=payload.get("url"),
    )


def parse_projects(payload: Any) -> list[AzureDevOpsProject]:
    projects: list[AzureDevOpsProject] = []
    for item in unwrap_value(payload):
        if not isinstance(item, dict):
            continue
        project = parse_project(item)
        if project is not None:
            projects.append(project)
    return projects


def parse_repository(payload: dict[str, Any]) -> AzureDevOpsRepository | None:
    repository_id = payload.get("id")
    name = payload.get("name")
    if not isinstance(repository_id, str) or not isinstance(name, str):
        return None

    project = payload.get("project")
    project_name = project.get("name") if isinstance(project, dict) else None

    return AzureDevOpsRepository(
        id=repository_id,
        name=name,
        project_name=str(project_name) if project_name is not None else None,
        default_branch=payload.get("defaultBranch"),
        remote_url=payload.get("remoteUrl"),
        web_url=payload.get("webUrl"),
    )


def parse_repositories(payload: Any) -> list[AzureDevOpsRepository]:
    repositories: list[AzureDevOpsRepository] = []
    for item in unwrap_value(payload):
        if not isinstance(item, dict):
            continue
        repository = parse_repository(item)
        if repository is not None:
            repositories.append(repository)
    return repositories


def parse_build(payload: dict[str, Any]) -> AzureDevOpsBuild | None:
    build_id = payload.get("id")
    build_number = payload.get("buildNumber")
    if not isinstance(build_id, int) or not isinstance(build_number, str):
        return None

    repository = payload.get("repository")
    repository_name = repository.get("name") if isinstance(repository, dict) else None

    return AzureDevOpsBuild(
        id=build_id,
        build_number=build_number,
        status=payload.get("status"),
        result=payload.get("result"),
        source_version=payload.get("sourceVersion"),
        repository_name=str(repository_name) if repository_name is not None else None,
        author=_display_name(payload.get("requestedBy")),
        queued_time=_parse_timestamp(payload.get("queueTime")),
        finish_time=_parse_timestamp(payload.get("finishTime")),
    )


def parse_builds(payload: Any) -> list[AzureDevOpsBuild]:
    builds: list[AzureDevOpsBuild] = []
    for item in unwrap_value(payload):
        if not isinstance(item, dict):
            continue
        build = parse_build(item)
        if build is not None:
            builds.append(build)
    return builds


def parse_release(payload: dict[str, Any]) -> AzureDevOpsRelease | None:
    release_id = payload.get("id")
    name = payload.get("name")
    if not isinstance(release_id, int) or not isinstance(name, str):
        return None

    definition = payload.get("releaseDefinition")
    definition_name = (
        definition.get("name") if isinstance(definition, dict) else None
    )

    return AzureDevOpsRelease(
        id=release_id,
        name=name,
        status=payload.get("status"),
        definition_name=str(definition_name) if definition_name is not None else None,
        author=_display_name(payload.get("createdBy")),
        created_on=_parse_timestamp(payload.get("createdOn")),
    )


def parse_releases(payload: Any) -> list[AzureDevOpsRelease]:
    releases: list[AzureDevOpsRelease] = []
    for item in unwrap_value(payload):
        if not isinstance(item, dict):
            continue
        release = parse_release(item)
        if release is not None:
            releases.append(release)
    return releases


def parse_deployment(payload: dict[str, Any]) -> AzureDevOpsDeployment | None:
    deployment_id = payload.get("id")
    if not isinstance(deployment_id, int):
        return None

    release = payload.get("release")
    release_id = release.get("id") if isinstance(release, dict) else None
    release_name = release.get("name") if isinstance(release, dict) else None

    environment = payload.get("releaseEnvironment") or payload.get("environment")
    environment_name = (
        environment.get("name") if isinstance(environment, dict) else None
    )

    return AzureDevOpsDeployment(
        id=deployment_id,
        release_id=int(release_id) if isinstance(release_id, int) else None,
        release_name=str(release_name) if release_name is not None else None,
        environment_name=(
            str(environment_name) if environment_name is not None else None
        ),
        status=payload.get("deploymentStatus") or payload.get("status"),
        author=_display_name(
            payload.get("requestedFor") or payload.get("requestedBy")
        ),
        started_on=_parse_timestamp(
            payload.get("startedOn") or payload.get("queueTime")
        ),
        completed_on=_parse_timestamp(
            payload.get("completedOn") or payload.get("modifiedOn")
        ),
    )


def parse_deployments(payload: Any) -> list[AzureDevOpsDeployment]:
    deployments: list[AzureDevOpsDeployment] = []
    for item in unwrap_value(payload):
        if not isinstance(item, dict):
            continue
        deployment = parse_deployment(item)
        if deployment is not None:
            deployments.append(deployment)
    return deployments


def parse_commit(payload: dict[str, Any]) -> AzureDevOpsCommit | None:
    commit_id = payload.get("commitId")
    if not isinstance(commit_id, str):
        return None

    comment = payload.get("comment")
    if not isinstance(comment, str):
        return None

    author_block = payload.get("author")
    author = None
    committed_on = None
    if isinstance(author_block, dict):
        author = author_block.get("name")
        committed_on = _parse_timestamp(author_block.get("date"))
        if author is not None:
            author = str(author)

    return AzureDevOpsCommit(
        commit_id=commit_id,
        message=comment,
        author=author,
        committed_on=committed_on,
        url=payload.get("url"),
    )


def parse_commits(payload: Any) -> list[AzureDevOpsCommit]:
    commits: list[AzureDevOpsCommit] = []
    for item in unwrap_value(payload):
        if not isinstance(item, dict):
            continue
        commit = parse_commit(item)
        if commit is not None:
            commits.append(commit)
    return commits


def parse_changed_files(payload: Any) -> list[AzureDevOpsChangedFile]:
    files: list[AzureDevOpsChangedFile] = []
    items: list[Any]
    if isinstance(payload, dict) and isinstance(payload.get("changes"), list):
        items = payload["changes"]
    else:
        items = unwrap_value(payload)

    for item in items:
        if not isinstance(item, dict):
            continue
        item_payload = item.get("item")
        if not isinstance(item_payload, dict):
            continue
        path = item_payload.get("path")
        if not isinstance(path, str):
            continue
        files.append(
            AzureDevOpsChangedFile(
                path=path,
                change_type=item.get("changeType"),
            )
        )
    return files
