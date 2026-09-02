"""Azure DevOps API resource types."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AzureDevOpsProject(BaseModel):
    """An Azure DevOps project."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str | None = None
    state: str | None = None
    url: str | None = None


class AzureDevOpsRepository(BaseModel):
    """A Git repository in Azure DevOps."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    project_name: str | None = None
    default_branch: str | None = None
    remote_url: str | None = None
    web_url: str | None = None


class AzureDevOpsBuild(BaseModel):
    """A pipeline build."""

    model_config = ConfigDict(extra="ignore")

    id: int
    build_number: str
    status: str | None = None
    result: str | None = None
    source_version: str | None = None
    repository_name: str | None = None
    author: str | None = None
    queued_time: datetime | None = None
    finish_time: datetime | None = None


class AzureDevOpsRelease(BaseModel):
    """A classic release pipeline release."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    status: str | None = None
    definition_name: str | None = None
    author: str | None = None
    created_on: datetime | None = None


class AzureDevOpsDeployment(BaseModel):
    """A release environment deployment."""

    model_config = ConfigDict(extra="ignore")

    id: int
    release_id: int | None = None
    release_name: str | None = None
    environment_name: str | None = None
    status: str | None = None
    author: str | None = None
    started_on: datetime | None = None
    completed_on: datetime | None = None


class AzureDevOpsCommit(BaseModel):
    """A Git commit."""

    model_config = ConfigDict(extra="ignore")

    commit_id: str
    message: str
    author: str | None = None
    committed_on: datetime | None = None
    url: str | None = None


class AzureDevOpsChangedFile(BaseModel):
    """A file changed in a commit."""

    model_config = ConfigDict(extra="ignore")

    path: str
    change_type: str | None = None
