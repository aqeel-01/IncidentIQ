"""Tenancy management API: organizations, projects, users, and roles."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUserDep,
    SettingsDep,
    raise_authz_http,
    require_project_role,
)
from app.db.models.enums import ProjectRole
from app.db.session import get_db
from app.domain.auth import (
    AuthenticationError,
    AuthorizationError,
    AuthService,
    AuthValidationError,
)

router = APIRouter(prefix="/api/v1", tags=["tenancy"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class OrganizationResponse(BaseModel):
    id: int
    name: str
    slug: str

    model_config = ConfigDict(frozen=True)


class ProjectResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True, frozen=True)


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int

    model_config = ConfigDict(frozen=True)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class UserCreatedResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    organization_id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True, frozen=True)


class MembershipResponse(BaseModel):
    id: int
    user_id: int
    project_id: int
    role: ProjectRole
    email: str | None = None
    full_name: str | None = None

    model_config = ConfigDict(frozen=True)


class MembershipListResponse(BaseModel):
    items: list[MembershipResponse]
    total: int

    model_config = ConfigDict(frozen=True)


class UpsertMembershipRequest(BaseModel):
    user_id: int
    role: ProjectRole


class RoleCatalogResponse(BaseModel):
    items: list[ProjectRole]

    model_config = ConfigDict(frozen=True)


@router.get("/roles", response_model=RoleCatalogResponse)
async def list_roles(_user: CurrentUserDep) -> RoleCatalogResponse:
    return RoleCatalogResponse(items=list(ProjectRole))


@router.get("/organizations/me", response_model=OrganizationResponse)
async def get_my_organization(
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> OrganizationResponse:
    profile = await AuthService(session, settings).get_profile(user.id)
    return OrganizationResponse(
        id=profile.organization_id,
        name=profile.organization_name,
        slug=profile.organization_slug,
    )


@router.get("/projects", response_model=ProjectListResponse)
async def list_my_projects(
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> ProjectListResponse:
    projects = await AuthService(session, settings).list_projects_for_user(user)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(item) for item in projects],
        total=len(projects),
    )


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: CreateProjectRequest,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> ProjectResponse:
    service = AuthService(session, settings)
    try:
        project = await service.create_project(
            actor=user,
            name=body.name,
            slug=body.slug,
        )
        await session.commit()
    except AuthorizationError as exc:
        raise_authz_http(exc)
    except AuthValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ProjectResponse.model_validate(project)


@router.post(
    "/users",
    response_model=UserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    body: CreateUserRequest,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> UserCreatedResponse:
    service = AuthService(session, settings)
    try:
        created = await service.create_organization_user(
            actor=user,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
        )
        await session.commit()
    except AuthorizationError as exc:
        raise_authz_http(exc)
    except AuthValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return UserCreatedResponse.model_validate(created)


@router.get(
    "/projects/{project_id}/memberships",
    response_model=MembershipListResponse,
)
async def list_memberships(
    project_id: int,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MembershipListResponse:
    await require_project_role(
        session=session,
        settings=settings,
        user=user,
        project_id=project_id,
        minimum_role=ProjectRole.ADMIN,
    )
    items = await AuthService(session, settings).list_memberships(project_id)
    return MembershipListResponse(
        items=[
            MembershipResponse(
                id=item.id,
                user_id=item.user_id,
                project_id=item.project_id,
                role=item.role,
                email=item.user.email if item.user is not None else None,
                full_name=item.user.full_name if item.user is not None else None,
            )
            for item in items
        ],
        total=len(items),
    )


@router.put(
    "/projects/{project_id}/memberships",
    response_model=MembershipResponse,
)
async def upsert_membership(
    project_id: int,
    body: UpsertMembershipRequest,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MembershipResponse:
    service = AuthService(session, settings)
    try:
        membership = await service.upsert_membership(
            actor=user,
            project_id=project_id,
            user_id=body.user_id,
            role=body.role,
        )
        await session.commit()
        await session.refresh(membership, attribute_names=["user"])
    except (LookupError, AuthorizationError, AuthenticationError) as exc:
        raise_authz_http(exc)
    except AuthValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MembershipResponse(
        id=membership.id,
        user_id=membership.user_id,
        project_id=membership.project_id,
        role=membership.role,
        email=membership.user.email if membership.user is not None else None,
        full_name=membership.user.full_name if membership.user is not None else None,
    )


@router.delete(
    "/projects/{project_id}/memberships/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_membership(
    project_id: int,
    user_id: int,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    service = AuthService(session, settings)
    try:
        await service.delete_membership(
            actor=user,
            project_id=project_id,
            user_id=user_id,
        )
        await session.commit()
    except (LookupError, AuthorizationError, AuthenticationError) as exc:
        raise_authz_http(exc)
    except AuthValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
