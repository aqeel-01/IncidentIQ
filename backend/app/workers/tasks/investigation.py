"""Investigation background tasks."""

from __future__ import annotations

from celery.exceptions import MaxRetriesExceededError

from app.core.config import get_settings
from app.domain.investigation import InvestigationJobError, InvestigationJobRunner
from app.workers.async_runner import run_async, run_with_session
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="investigation.run",
    acks_late=True,
)
def run_investigation_job(self, job_id: str) -> dict[str, str]:
    """Execute an investigation job in the background."""

    settings = get_settings()

    async def _execute(session, resolved_settings):
        runner = InvestigationJobRunner(session, resolved_settings)
        try:
            result = await runner.run(job_id)
        except InvestigationJobError:
            await session.commit()
            raise
        except Exception as exc:
            await runner.mark_failed(job_id, error_message=str(exc))
            raise
        await session.commit()
        return {
            "job_id": result.job_id,
            "incident_id": str(result.incident_id),
            "status": result.status.value,
            "stage": result.stage.value,
        }

    try:
        return run_async(run_with_session(settings, _execute))
    except InvestigationJobError:
        raise
    except Exception as exc:
        run_async(_mark_retry(settings, job_id, str(exc)))
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            run_async(_mark_failed(settings, job_id, str(exc)))
            raise


async def _mark_retry(settings, job_id: str, error_message: str) -> None:
    async def _handler(session, _settings):
        runner = InvestigationJobRunner(session, _settings)
        await runner.mark_retrying(job_id, error_message=error_message)
        await session.commit()

    await run_with_session(settings, _handler)


async def _mark_failed(settings, job_id: str, error_message: str) -> None:
    async def _handler(session, _settings):
        runner = InvestigationJobRunner(session, _settings)
        await runner.mark_failed(job_id, error_message=error_message)
        await session.commit()

    await run_with_session(settings, _handler)
