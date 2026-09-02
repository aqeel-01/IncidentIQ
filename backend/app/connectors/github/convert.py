"""Convert GitHub resources into canonical deployment events."""

from __future__ import annotations

from app.connectors.github.types import GitHubDeployment, GitHubRelease
from app.domain.events import DeploymentEvent


def github_deployment_to_event(
    deployment: GitHubDeployment,
    *,
    repository: str,
    source: str,
    changed_files: list[str] | None = None,
    service: str | None = None,
    environment: str | None = None,
) -> DeploymentEvent:
    """Map a GitHub deployment to a :class:`DeploymentEvent`."""

    return DeploymentEvent(
        timestamp=deployment.created_at,
        source=source,
        source_type="github",
        source_id=str(deployment.id),
        service=service,
        environment=environment or deployment.environment,
        version=deployment.ref,
        commit_sha=deployment.sha,
        author=deployment.author,
        repository=repository,
        changed_files=list(changed_files or []),
        raw_data={
            "deployment_id": deployment.id,
            "ref": deployment.ref,
            "sha": deployment.sha,
            "environment": deployment.environment,
            "description": deployment.description,
        },
    )


def github_release_to_event(
    release: GitHubRelease,
    *,
    repository: str,
    source: str,
    changed_files: list[str] | None = None,
    service: str | None = None,
    environment: str | None = None,
) -> DeploymentEvent | None:
    """Map a GitHub release to a :class:`DeploymentEvent`."""

    if release.published_at is None:
        return None

    return DeploymentEvent(
        timestamp=release.published_at,
        source=source,
        source_type="github",
        source_id=str(release.id),
        service=service,
        environment=environment,
        version=release.tag_name,
        commit_sha=release.target_commitish,
        author=release.author,
        repository=repository,
        changed_files=list(changed_files or []),
        raw_data={
            "release_id": release.id,
            "tag_name": release.tag_name,
            "target_commitish": release.target_commitish,
            "name": release.name,
            "html_url": release.html_url,
        },
    )
