"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.domain.investigation import (
    InvestigationTaskDispatcher,
    investigation_task_dispatcher,
)
from app.workers.dispatch import dispatch_investigation_job


def get_investigation_dispatcher() -> InvestigationTaskDispatcher:
    """Return the Celery-backed investigation job dispatcher."""

    return investigation_task_dispatcher(dispatch_investigation_job)


InvestigationDispatcherDep = Annotated[
    InvestigationTaskDispatcher,
    Depends(get_investigation_dispatcher),
]
