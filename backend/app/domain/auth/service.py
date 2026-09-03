"""Authentication and authorization service."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.db.models import (
    Organization,
    Project,
    ProjectMembership,
    ProjectRole,
    User,
)
from app.domain.auth.passwords import (
    hash_password,
    verify_password_or_dummy,
)
from app.domain.auth.roles import role_satisfies
from app.domain.auth.tokens import TokenError, create_access_token, decode_access_token

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AuthenticationError(Exception):
    """Raised when credentials or tokens are invalid."""


class AuthorizationError(Exception):
    """Raised when the caller lacks permission for a resource."""


class AuthValidationError(ValueError):
    """Raised for invalid auth/tenancy input."""


@dataclass(frozen=True, slots=True)
class MembershipView:
    project_id: int
    project_name: str
    project_slug: str
    organization_id: int
    role: ProjectRole


@dataclass(frozen=True, slots=True)
class UserProfile:
    id: int
    email: str
    full_name: str | None
    organization_id: int
    organization_name: str
    organization_slug: str
    is_active: bool
    memberships: tuple[MembershipView, ...]


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    token_type: str
    user: UserProfile


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    organization: Organization
    project: Project
    user: User
    membership: ProjectMembership
    token: TokenPair


class AuthService:
    """Login, bootstrap, membership management, and project authorization."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def bootstrap(
        self,
        *,
        organization_name: str,
        organization_slug: str,
        project_name: str,
        project_slug: str,
        email: str,
        password: str,
        full_name: str | None = None,
    ) -> BootstrapResult:
        """Create the first org/project/admin when the database has no users."""

        if self._settings.resolved_auth_bootstrap_disabled:
            msg = "bootstrap is disabled"
            raise AuthValidationError(msg)

        existing = await self._session.scalar(select(func.count()).select_from(User))
        if existing and existing > 0:
            msg = "bootstrap is only allowed when no users exist"
            raise AuthValidationError(msg)

        org_slug = _normalize_slug(organization_slug)
        proj_slug = _normalize_slug(project_slug)
        email_norm = _normalize_email(email)
        _require_password(password)

        org = Organization(name=organization_name.strip(), slug=org_slug)
        project = Project(
            name=project_name.strip(),
            slug=proj_slug,
            organization=org,
        )
        user = User(
            email=email_norm,
            hashed_password=hash_password(password),
            full_name=(full_name or "").strip() or None,
            organization=org,
            is_active=True,
        )
        membership = ProjectMembership(
            user=user,
            project=project,
            role=ProjectRole.ADMIN,
        )
        self._session.add_all([org, project, user, membership])
        await self._session.flush()

        profile = await self.get_profile(user.id)
        token = TokenPair(
            access_token=create_access_token(
                settings=self._settings,
                subject=str(user.id),
                claims={"org_id": org.id},
            ),
            token_type="bearer",
            user=profile,
        )
        return BootstrapResult(
            organization=org,
            project=project,
            user=user,
            membership=membership,
            token=token,
        )

    async def login(self, *, email: str, password: str) -> TokenPair:
        email_norm = _normalize_email(email)
        user = await self._session.scalar(
            select(User)
            .where(User.email == email_norm)
            .options(
                selectinload(User.organization),
                selectinload(User.memberships).selectinload(ProjectMembership.project),
            )
        )
        hashed = None if user is None else user.hashed_password
        if not verify_password_or_dummy(password, hashed):
            msg = "invalid email or password"
            raise AuthenticationError(msg)
        assert user is not None
        if not user.is_active:
            msg = "user account is disabled"
            raise AuthenticationError(msg)

        profile = self._to_profile(user)
        return TokenPair(
            access_token=create_access_token(
                settings=self._settings,
                subject=str(user.id),
                claims={"org_id": user.organization_id},
            ),
            token_type="bearer",
            user=profile,
        )

    async def authenticate_token(self, token: str) -> User:
        try:
            payload = decode_access_token(settings=self._settings, token=token)
        except TokenError as exc:
            raise AuthenticationError(str(exc)) from exc

        try:
            user_id = int(payload["sub"])
        except (TypeError, ValueError) as exc:
            msg = "invalid access token subject"
            raise AuthenticationError(msg) from exc

        user = await self._session.get(User, user_id)
        if user is None or not user.is_active:
            msg = "user not found or inactive"
            raise AuthenticationError(msg)
        return user

    async def get_profile(self, user_id: int) -> UserProfile:
        user = await self._session.scalar(
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.organization),
                selectinload(User.memberships).selectinload(ProjectMembership.project),
            )
        )
        if user is None:
            msg = f"user {user_id} not found"
            raise LookupError(msg)
        return self._to_profile(user)

    async def require_project_role(
        self,
        user: User,
        project_id: int,
        minimum_role: ProjectRole,
    ) -> ProjectMembership:
        """Authorize ``user`` for ``project_id`` at ``minimum_role``.

        Missing projects raise :class:`LookupError` (404). Missing membership or
        insufficient role raise :class:`AuthorizationError` (403).
        """

        project = await self._session.get(Project, project_id)
        if project is None:
            msg = f"project {project_id} not found"
            raise LookupError(msg)

        if project.organization_id != user.organization_id:
            msg = "not authorized for this project"
            raise AuthorizationError(msg)

        membership = await self._session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.user_id == user.id,
                ProjectMembership.project_id == project_id,
            )
        )
        if membership is None:
            msg = "not authorized for this project"
            raise AuthorizationError(msg)

        if not role_satisfies(membership.role, minimum_role):
            msg = (
                f"role {membership.role.value} is insufficient; "
                f"requires {minimum_role.value}"
            )
            raise AuthorizationError(msg)
        return membership

    async def create_organization_user(
        self,
        *,
        actor: User,
        email: str,
        password: str,
        full_name: str | None = None,
    ) -> User:
        """Create a user in the actor's organization (ADMIN on any project)."""

        await self._require_org_admin(actor)
        email_norm = _normalize_email(email)
        _require_password(password)

        existing = await self._session.scalar(
            select(User.id).where(User.email == email_norm)
        )
        if existing is not None:
            msg = f"email {email_norm} is already registered"
            raise AuthValidationError(msg)

        user = User(
            organization_id=actor.organization_id,
            email=email_norm,
            hashed_password=hash_password(password),
            full_name=(full_name or "").strip() or None,
            is_active=True,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def create_project(
        self,
        *,
        actor: User,
        name: str,
        slug: str,
    ) -> Project:
        await self._require_org_admin(actor)
        proj_slug = _normalize_slug(slug)
        existing = await self._session.scalar(
            select(Project.id).where(
                Project.organization_id == actor.organization_id,
                Project.slug == proj_slug,
            )
        )
        if existing is not None:
            msg = f"project slug {proj_slug!r} already exists in organization"
            raise AuthValidationError(msg)

        project = Project(
            organization_id=actor.organization_id,
            name=name.strip(),
            slug=proj_slug,
        )
        membership = ProjectMembership(
            user_id=actor.id,
            project=project,
            role=ProjectRole.ADMIN,
        )
        self._session.add_all([project, membership])
        await self._session.flush()
        return project

    async def list_projects_for_user(self, user: User) -> list[Project]:
        result = await self._session.scalars(
            select(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(ProjectMembership.user_id == user.id)
            .order_by(Project.name.asc())
        )
        return list(result.all())

    async def list_memberships(self, project_id: int) -> list[ProjectMembership]:
        result = await self._session.scalars(
            select(ProjectMembership)
            .where(ProjectMembership.project_id == project_id)
            .options(selectinload(ProjectMembership.user))
            .order_by(ProjectMembership.id.asc())
        )
        return list(result.all())

    async def upsert_membership(
        self,
        *,
        actor: User,
        project_id: int,
        user_id: int,
        role: ProjectRole,
    ) -> ProjectMembership:
        await self.require_project_role(actor, project_id, ProjectRole.ADMIN)

        target = await self._session.get(User, user_id)
        if target is None:
            msg = f"user {user_id} not found"
            raise LookupError(msg)
        if target.organization_id != actor.organization_id:
            msg = "user is not in the same organization"
            raise AuthorizationError(msg)

        membership = await self._session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.user_id == user_id,
                ProjectMembership.project_id == project_id,
            )
        )
        if membership is None:
            membership = ProjectMembership(
                user_id=user_id,
                project_id=project_id,
                role=role,
            )
            self._session.add(membership)
        else:
            membership.role = role
        await self._session.flush()
        return membership

    async def delete_membership(
        self,
        *,
        actor: User,
        project_id: int,
        user_id: int,
    ) -> None:
        await self.require_project_role(actor, project_id, ProjectRole.ADMIN)
        membership = await self._session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.user_id == user_id,
                ProjectMembership.project_id == project_id,
            )
        )
        if membership is None:
            msg = f"membership for user {user_id} on project {project_id} not found"
            raise LookupError(msg)

        admin_count = await self._session.scalar(
            select(func.count())
            .select_from(ProjectMembership)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.role == ProjectRole.ADMIN,
            )
        )
        if (
            membership.role == ProjectRole.ADMIN
            and admin_count is not None
            and admin_count <= 1
        ):
            msg = "cannot remove the last ADMIN from a project"
            raise AuthValidationError(msg)

        await self._session.delete(membership)
        await self._session.flush()

    async def _require_org_admin(self, actor: User) -> None:
        membership = await self._session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.user_id == actor.id,
                ProjectMembership.role == ProjectRole.ADMIN,
            )
        )
        if membership is None:
            msg = "organization administration requires ADMIN on at least one project"
            raise AuthorizationError(msg)

    def _to_profile(self, user: User) -> UserProfile:
        memberships = tuple(
            MembershipView(
                project_id=item.project_id,
                project_name=item.project.name,
                project_slug=item.project.slug,
                organization_id=item.project.organization_id,
                role=item.role,
            )
            for item in sorted(user.memberships, key=lambda m: m.project_id)
        )
        return UserProfile(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            organization_id=user.organization_id,
            organization_name=user.organization.name,
            organization_slug=user.organization.slug,
            is_active=user.is_active,
            memberships=memberships,
        )


def _normalize_email(email: str) -> str:
    value = email.strip().lower()
    if not value or "@" not in value:
        msg = "email is required"
        raise AuthValidationError(msg)
    return value


def _normalize_slug(slug: str) -> str:
    value = slug.strip().lower()
    if not _SLUG_RE.fullmatch(value):
        msg = "slug must be lowercase alphanumeric with optional hyphens"
        raise AuthValidationError(msg)
    return value


def _require_password(password: str) -> None:
    if len(password) < 8:
        msg = "password must be at least 8 characters"
        raise AuthValidationError(msg)
