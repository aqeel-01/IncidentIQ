"""Top-level API router aggregation.

Feature routers are included here as they are implemented. For now only the
health router is wired up.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import alerts, health, incidents, logs, timeline

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(logs.router)
api_router.include_router(incidents.router)
api_router.include_router(timeline.router)
api_router.include_router(alerts.router)
