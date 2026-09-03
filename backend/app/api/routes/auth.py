"""Authentication API: bootstrap, login, and current user profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SettingsDep
from app.db.models.enums import ProjectRole
from app.db.session import get_db
from app.domain.auth import (
    AuthenticationError,
    AuthService,
    AuthValidationError,
    MembershipView,
    TokenPair,
    UserProfile,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


class MembershipResponse(BaseModel):
    project_id: int
    project_name: str
    project_slug: str
    organization_id: int
    role: ProjectRole

    model_config = ConfigDict(frozen=True)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    organization_id: int
    organization_name: str
    organization_slug: str
    is_active: bool
    memberships: list[MembershipResponse]

    model_config = ConfigDict(frozen=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

    model_config = ConfigDict(frozen=True)


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str = Field(min_length=1, max_length=255)
    project_name: str = Field(min_length=1, max_length=255)
    project_slug: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class BootstrapResponse(BaseModel):
    organization_id: int
    project_id: int
    user: UserResponse
    access_token: str
    token_type: str

    model_config = ConfigDict(frozen=True)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


def _membership_response(item: MembershipView) -> MembershipResponse:
    return MembershipResponse(
        project_id=item.project_id,
        project_name=item.project_name,
        project_slug=item.project_slug,
        organization_id=item.organization_id,
        role=item.role,
    )


def _user_response(profile: UserProfile) -> UserResponse:
    return UserResponse(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        organization_id=profile.organization_id,
        organization_name=profile.organization_name,
        organization_slug=profile.organization_slug,
        is_active=profile.is_active,
        memberships=[_membership_response(item) for item in profile.memberships],
    )


def _token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        token_type=pair.token_type,
        user=_user_response(pair.user),
    )


@router.post(
    "/bootstrap",
    response_model=BootstrapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap(
    body: BootstrapRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> BootstrapResponse:
    """Create the first organization, project, and ADMIN user."""

    service = AuthService(session, settings)
    try:
        result = await service.bootstrap(
            organization_name=body.organization_name,
            organization_slug=body.organization_slug,
            project_name=body.project_name,
            project_slug=body.project_slug,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
        )
        await session.commit()
    except AuthValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return BootstrapResponse(
        organization_id=result.organization.id,
        project_id=result.project.id,
        user=_user_response(result.token.user),
        access_token=result.token.access_token,
        token_type=result.token.token_type,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    service = AuthService(session, settings)
    try:
        pair = await service.login(email=body.email, password=body.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AuthValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _token_response(pair)


@router.get("/me", response_model=UserResponse)
async def me(
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> UserResponse:
    profile = await AuthService(session, settings).get_profile(user.id)
    return _user_response(profile)
