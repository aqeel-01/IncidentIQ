"""Investigation job execution and submission."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider
from app.core.config import Settings
from app.db.models.incident import Incident
from app.db.models.investigation_job import (
    InvestigationJob,
    InvestigationJobStatus,
    InvestigationStage,
)
from app.db.models.project import Project
from app.domain.investigation.orchestrator import InvestigationOrchestrator
from app.domain.investigation.sources import InvestigationSources
from app.domain.investigation.types import (
    InvestigationJobResult,
    InvestigationJobSnapshot,
)


class InvestigationTaskDispatcher(Protocol):
    """Dispatches investigation jobs to a background worker."""

    def dispatch(self, job_id: str) -> str:
        """Enqueue ``job_id`` and return the worker task identifier."""


class InvestigationJobService:
    """Submit and query investigation background jobs."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        dispatcher: InvestigationTaskDispatcher | None = None,
    ) -> None:
        self._session = session
        self._dispatcher = dispatcher

    async def submit_for_incident(self, incident_id: int) -> InvestigationJobSnapshot:
        """Queue an investigation for ``incident_id``."""

        result = await self._session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if incident is None:
            msg = f"incident {incident_id} not found"
            raise LookupError(msg)

        return await self.submit(
            project_id=incident.project_id,
            incident_id=incident_id,
        )

    async def submit(
        self,
        *,
        project_id: int,
        incident_id: int,
    ) -> InvestigationJobSnapshot:
        await self._ensure_incident(project_id=project_id, incident_id=incident_id)

        if self._dispatcher is None:
            msg = "investigation dispatcher is not configured"
            raise RuntimeError(msg)

        job = InvestigationJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            incident_id=incident_id,
            status=InvestigationJobStatus.QUEUED,
            stage=InvestigationStage.QUEUED,
            stage_artifacts={},
        )
        self._session.add(job)
        await self._session.flush()

        task_id = self._dispatcher.dispatch(job.id)
        job.celery_task_id = task_id
        await self._session.flush()
        await self._session.refresh(job)
        return _snapshot(job)

    async def get(self, job_id: str) -> InvestigationJobSnapshot | None:
        job = await self._load_job(job_id)
        if job is None:
            return None
        return _snapshot(job)

    async def _ensure_incident(self, *, project_id: int, incident_id: int) -> None:
        result = await self._session.execute(
            select(Incident.id).where(
                Incident.id == incident_id,
                Incident.project_id == project_id,
            )
        )
        if result.scalar_one_or_none() is None:
            msg = f"incident {incident_id} not found in project {project_id}"
            raise LookupError(msg)

        project_exists = await self._session.execute(
            select(Project.id).where(Project.id == project_id)
        )
        if project_exists.scalar_one_or_none() is None:
            msg = f"project {project_id} not found"
            raise LookupError(msg)

    async def _load_job(self, job_id: str) -> InvestigationJob | None:
        result = await self._session.execute(
            select(InvestigationJob).where(InvestigationJob.id == job_id)
        )
        return result.scalar_one_or_none()


class InvestigationJobRunner:
    """Execute a queued investigation job through the full pipeline."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        sources: InvestigationSources | None = None,
        ai_provider: AIProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._sources = sources
        self._ai_provider = ai_provider

    async def run(self, job_id: str) -> InvestigationJobResult:
        orchestrator = InvestigationOrchestrator(
            self._session,
            self._settings,
            sources=self._sources,
            ai_provider=self._ai_provider,
        )
        return await orchestrator.run(job_id)

    async def mark_retrying(self, job_id: str, *, error_message: str) -> None:
        job = await self._load_job(job_id)
        if job is None:
            return

        job.status = InvestigationJobStatus.RETRYING
        job.error_message = error_message
        await self._session.flush()

    async def mark_failed(self, job_id: str, *, error_message: str) -> None:
        job = await self._load_job(job_id)
        if job is None:
            return

        job.status = InvestigationJobStatus.FAILED
        job.stage = InvestigationStage.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        await self._session.flush()

    async def _load_job(self, job_id: str) -> InvestigationJob | None:
        result = await self._session.execute(
            select(InvestigationJob).where(InvestigationJob.id == job_id)
        )
        return result.scalar_one_or_none()


def investigation_task_dispatcher(
    dispatch_fn: Callable[[str], str],
) -> InvestigationTaskDispatcher:
    """Wrap a callable as an :class:`InvestigationTaskDispatcher`."""

    class _Dispatcher:
        def dispatch(self, job_id: str) -> str:
            return dispatch_fn(job_id)

    return _Dispatcher()


def _snapshot(job: InvestigationJob) -> InvestigationJobSnapshot:
    return InvestigationJobSnapshot(
        id=job.id,
        project_id=job.project_id,
        incident_id=job.incident_id,
        status=job.status,
        stage=job.stage,
        stage_artifacts=dict(job.stage_artifacts or {}),
        celery_task_id=job.celery_task_id,
        attempt_count=job.attempt_count,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
