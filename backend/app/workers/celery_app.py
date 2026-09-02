"""Celery application factory."""

from __future__ import annotations

from celery import Celery

from app.core.config import Settings, get_settings
from app.workers.config import celery_config_from_settings

celery_app = Celery("incidentiq")


def configure_celery_app(
    app: Celery,
    settings: Settings | None = None,
) -> Celery:
    """Apply IncidentIQ Celery settings and autodiscover tasks."""

    resolved_settings = settings or get_settings()
    app.conf.update(celery_config_from_settings(resolved_settings))
    app.conf.update(
        task_autoretry_for=(Exception,),
        task_retry_backoff=resolved_settings.celery_task_retry_backoff_seconds,
        task_retry_backoff_max=resolved_settings.celery_task_retry_backoff_max_seconds,
        task_max_retries=resolved_settings.celery_task_max_retries,
    )
    app.autodiscover_tasks(["app.workers.tasks"])
    return app


configure_celery_app(celery_app)
