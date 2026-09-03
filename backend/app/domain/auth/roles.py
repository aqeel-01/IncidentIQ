"""Project role ordering helpers."""

from __future__ import annotations

from app.db.models.enums import ProjectRole

ROLE_RANK: dict[ProjectRole, int] = {
    ProjectRole.VIEWER: 1,
    ProjectRole.ENGINEER: 2,
    ProjectRole.ADMIN: 3,
}


def role_satisfies(actual: ProjectRole, required: ProjectRole) -> bool:
    """Return True when ``actual`` is at least as privileged as ``required``."""

    return ROLE_RANK[actual] >= ROLE_RANK[required]
