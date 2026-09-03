"""FastAPI application entrypoint.

Exposes an application factory (:func:`create_app`) and a module-level ``app``
instance for ASGI servers, e.g. ``uvicorn app.main:app``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import MetricsMiddleware, RateLimitMiddleware
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure a FastAPI application instance."""

    configure_logging()
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Engine creation does not open a connection, so the app starts even if
        # the database is temporarily unreachable (readiness reports that).
        app.state.db = Database(settings)
        try:
            yield
        finally:
            await app.state.db.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="AI-powered production incident investigation and RCA platform.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Middleware runs in reverse registration order on the request path.
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(MetricsMiddleware)

    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router)
    return app


app = create_app()
