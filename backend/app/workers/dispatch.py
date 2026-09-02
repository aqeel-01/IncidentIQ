"""Dispatch investigation jobs to Celery."""

from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks.investigation import run_investigation_job


def dispatch_investigation_job(job_id: str) -> str:
    """Enqueue an investigation job and return the Celery task id."""

    result = run_investigation_job.apply_async(
        args=[job_id],
        queue=celery_app.conf.task_default_queue,
    )
    return result.id
