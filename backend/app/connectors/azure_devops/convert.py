"""Convert Azure DevOps resources into canonical deployment events."""

from __future__ import annotations

from app.connectors.azure_devops.types import (
    AzureDevOpsBuild,
    AzureDevOpsDeployment,
    AzureDevOpsRelease,
)
from app.domain.events import DeploymentEvent


def azure_build_to_event(
    build: AzureDevOpsBuild,
    *,
    repository: str,
    source: str,
    changed_files: list[str] | None = None,
    service: str | None = None,
    environment: str | None = None,
) -> DeploymentEvent | None:
    """Map a successful build to a :class:`DeploymentEvent`."""

    if build.result not in {None, "succeeded", "partiallySucceeded"}:
        return None

    timestamp = build.finish_time or build.queued_time
    if timestamp is None:
        return None

    return DeploymentEvent(
        timestamp=timestamp,
        source=source,
        source_type="azure_devops",
        source_id=str(build.id),
        service=service,
        environment=environment,
        version=build.build_number,
        commit_sha=build.source_version,
        author=build.author,
        repository=repository,
        changed_files=list(changed_files or []),
        raw_data={
            "build_id": build.id,
            "build_number": build.build_number,
            "status": build.status,
            "result": build.result,
            "source_version": build.source_version,
        },
    )


def azure_release_to_event(
    release: AzureDevOpsRelease,
    *,
    repository: str,
    source: str,
    changed_files: list[str] | None = None,
    service: str | None = None,
    environment: str | None = None,
) -> DeploymentEvent | None:
    """Map a release to a :class:`DeploymentEvent`."""

    if release.created_on is None:
        return None

    return DeploymentEvent(
        timestamp=release.created_on,
        source=source,
        source_type="azure_devops",
        source_id=str(release.id),
        service=service,
        environment=environment,
        version=release.name,
        commit_sha=None,
        author=release.author,
        repository=repository,
        changed_files=list(changed_files or []),
        raw_data={
            "release_id": release.id,
            "name": release.name,
            "status": release.status,
            "definition_name": release.definition_name,
        },
    )


def azure_deployment_to_event(
    deployment: AzureDevOpsDeployment,
    *,
    repository: str,
    source: str,
    changed_files: list[str] | None = None,
    service: str | None = None,
    environment: str | None = None,
) -> DeploymentEvent | None:
    """Map a release deployment to a :class:`DeploymentEvent`."""

    if deployment.status not in {None, "succeeded", "partiallySucceeded"}:
        return None

    timestamp = deployment.completed_on or deployment.started_on
    if timestamp is None:
        return None

    return DeploymentEvent(
        timestamp=timestamp,
        source=source,
        source_type="azure_devops",
        source_id=str(deployment.id),
        service=service,
        environment=environment or deployment.environment_name,
        version=deployment.release_name,
        commit_sha=None,
        author=deployment.author,
        repository=repository,
        changed_files=list(changed_files or []),
        raw_data={
            "deployment_id": deployment.id,
            "release_id": deployment.release_id,
            "release_name": deployment.release_name,
            "environment_name": deployment.environment_name,
            "status": deployment.status,
        },
    )
