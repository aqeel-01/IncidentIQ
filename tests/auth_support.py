"""Shared helpers for authenticating API tests."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Organization, Project, ProjectMembership, ProjectRole, User
from app.domain.auth.passwords import hash_password

TEST_PASSWORD = "password12"


async def create_user(
    session: AsyncSession,
    organization: Organization,
    *,
    email: str,
    role: ProjectRole | None = None,
    project: Project | None = None,
    password: str = TEST_PASSWORD,
    full_name: str | None = "Test User",
) -> User:
    """Create a user in ``organization``, optionally with a project membership."""

    user = User(
        organization_id=organization.id,
        email=email.lower(),
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    if project is not None and role is not None:
        session.add(
            ProjectMembership(
                user_id=user.id,
                project_id=project.id,
                role=role,
            )
        )
        await session.flush()
    return user


async def grant_role(
    session: AsyncSession,
    user: User,
    project: Project,
    role: ProjectRole,
) -> ProjectMembership:
    membership = ProjectMembership(
        user_id=user.id,
        project_id=project.id,
        role=role,
    )
    session.add(membership)
    await session.flush()
    return membership


async def create_principal(
    session: AsyncSession,
    *,
    email: str = "admin@acme.test",
    org_name: str = "Acme",
    org_slug: str = "acme",
) -> User:
    """Create a default organization + admin user with no project memberships."""

    org = Organization(name=org_name, slug=org_slug)
    session.add(org)
    await session.flush()
    user = await create_user(session, org, email=email, full_name="Admin")
    await session.commit()
    await session.refresh(user)
    return user


def install_current_user(app: FastAPI, user: User) -> None:
    """Override ``get_current_user`` to return ``user`` for the test app."""

    async def _current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _current_user
