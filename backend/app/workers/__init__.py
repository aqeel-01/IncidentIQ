"""Background worker integration."""

from app.workers.celery_app import celery_app, configure_celery_app
from app.workers.dispatch import dispatch_investigation_job

__all__ = [
    "celery_app",
    "configure_celery_app",
    "dispatch_investigation_job",
]
