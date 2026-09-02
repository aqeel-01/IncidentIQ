"""Celery worker configuration helpers."""

from __future__ import annotations

from app.core.config import Settings


def celery_config_from_settings(settings: Settings) -> dict[str, object]:
    """Build Celery configuration from application settings."""

    return {
        "broker_url": settings.resolved_celery_broker_url,
        "result_backend": settings.resolved_celery_result_backend,
        "task_default_queue": settings.celery_default_queue,
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "task_track_started": True,
        "worker_prefetch_multiplier": 1,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
        "task_routes": {
            "investigation.run": {"queue": settings.celery_default_queue},
        },
    }
