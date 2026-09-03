"""Prometheus metrics scrape endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.config import Settings, get_settings
from app.core.metrics import render_metrics

router = APIRouter(tags=["observability"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/metrics")
async def metrics(settings: SettingsDep) -> Response:
    """Expose Prometheus metrics for scraping.

    Does not require an external Prometheus server to be running. Scrapers can
    pull this endpoint when available; local startup never depends on it.
    """

    payload, content_type = render_metrics(
        broker_url=settings.resolved_celery_broker_url,
        queue=settings.celery_default_queue,
    )
    return Response(content=payload, media_type=content_type)
