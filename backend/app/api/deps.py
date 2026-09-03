"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import ProjectMembership, ProjectRole, User
from app.db.session import get_db
from app.domain.auth import AuthenticationError, AuthorizationError, AuthService
from app.domain.investigation import (
    InvestigationTaskDispatcher,
    investigation_task_dispatcher,
)
from app.workers.dispatch import dispatch_investigation_job

_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_investigation_dispatcher() -> InvestigationTaskDispatcher:
    """Return the Celery-backed investigation job dispatcher."""

    return investigation_task_dispatcher(dispatch_investigation_job)


InvestigationDispatcherDep = Annotated[
    InvestigationTaskDispatcher,
    Depends(get_investigation_dispatcher),
]


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> User:
    """Resolve the authenticated user from a Bearer access token."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return await AuthService(session, settings).authenticate_token(
            credentials.credentials
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def raise_authz_http(exc: Exception) -> None:
    """Map auth domain errors to HTTP responses (never returns)."""

    if isinstance(exc, LookupError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, AuthorizationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, AuthenticationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    raise exc


async def require_project_role(
    *,
    session: AsyncSession,
    settings: Settings,
    user: User,
    project_id: int,
    minimum_role: ProjectRole,
) -> ProjectMembership:
    """Authorize ``user`` for ``project_id`` or raise an HTTP error."""

    try:
        return await AuthService(session, settings).require_project_role(
            user,
            project_id,
            minimum_role,
        )
    except (LookupError, AuthorizationError, AuthenticationError) as exc:
        raise_authz_http(exc)
        raise  # pragma: no cover
