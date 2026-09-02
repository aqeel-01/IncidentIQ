"""GitHub API resource types."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GitHubRepository(BaseModel):
    """A GitHub repository returned by the REST API."""

    model_config = ConfigDict(extra="ignore")

    id: int
    full_name: str
    name: str
    private: bool = False
    default_branch: str | None = None
    html_url: str | None = None


class GitHubCommit(BaseModel):
    """A commit summary."""

    model_config = ConfigDict(extra="ignore")

    sha: str
    message: str
    author: str | None = None
    committed_at: datetime
    html_url: str | None = None


class GitHubPullRequest(BaseModel):
    """A pull request summary."""

    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    state: str
    author: str | None = None
    created_at: datetime
    merged_at: datetime | None = None
    head_sha: str | None = None
    html_url: str | None = None


class GitHubDeployment(BaseModel):
    """A deployment record."""

    model_config = ConfigDict(extra="ignore")

    id: int
    sha: str
    ref: str
    environment: str
    author: str | None = None
    created_at: datetime
    description: str | None = None


class GitHubRelease(BaseModel):
    """A release record."""

    model_config = ConfigDict(extra="ignore")

    id: int
    tag_name: str
    target_commitish: str
    author: str | None = None
    published_at: datetime | None = None
    name: str | None = None
    html_url: str | None = None


class GitHubChangedFile(BaseModel):
    """A file changed in a commit or pull request."""

    model_config = ConfigDict(extra="ignore")

    filename: str
    status: str | None = None
    additions: int = 0
    deletions: int = 0
    changes: int = 0
