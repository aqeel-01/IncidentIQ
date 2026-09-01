"""Health and readiness endpoints.

- ``GET /health`` is a liveness probe: it only confirms the API process is up
  and never depends on external services.
- ``GET /health/ready`` is a readiness probe: it verifies required
  infrastructure (PostgreSQL, Redis) and returns 503 when any required
  dependency is unavailable, without crashing the process.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.health import run_readiness_checks

router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, dict]


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness probe. Returns 200 as long as the API process is serving."""

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(
    settings: SettingsDep, request: Request, response: Response
) -> ReadinessResponse:
    """Readiness probe. Verifies required infrastructure dependencies."""

    database = getattr(request.app.state, "db", None)
    engine = database.engine if database is not None else None
    results = await run_readiness_checks(settings, engine)

    required_ok = all(r.healthy for r in results if r.required)
    if not required_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if required_ok else "not_ready",
        checks={r.name: r.as_dict() for r in results},
    )
