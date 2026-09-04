"""Domain-level event ingestion service.

Accepts validated canonical events, resolves project/service associations, and
persists rows to the ``events`` table. Source-specific connectors are out of
scope here — they produce :class:`~app.domain.events.CanonicalEventBase`
instances (or dicts that parse into them) and call this service.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import Severity
from app.db.models.event import Event as EventRow
from app.db.models.project import Project
from app.db.models.service import Service
from app.domain.events import (
    AlertEvent,
    CanonicalEventBase,
    DeploymentEvent,
    LogEvent,
    MetricEvent,
    TraceEvent,
    parse_event,
)

logger = logging.getLogger(__name__)

# Envelope fields stored as dedicated columns; everything else goes in
# ``normalized_data`` for traceability without losing type-specific detail.
_ENVELOPE_KEYS = frozenset(
    {
        "event_type",
        "timestamp",
        "source",
        "source_type",
        "source_id",
        "service",
        "environment",
        "raw_data",
        "normalized_data",
    }
)


class IngestionStatus(enum.StrEnum):
    ACCEPTED = "ACCEPTED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    SERVICE_NOT_FOUND = "SERVICE_NOT_FOUND"
    ERROR = "ERROR"


class EventIngestionResult(BaseModel):
    """Outcome for a single event in an ingestion batch."""

    model_config = {"frozen": True}

    index: int
    status: IngestionStatus
    event_id: int | None = None
    event_type: str | None = None
    service_id: int | None = None
    errors: list[str] = []


class BatchIngestionResult(BaseModel):
    """Aggregate outcome for a multi-event ingestion call."""

    model_config = {"frozen": True}

    project_id: int
    total: int
    accepted: int
    rejected: int
    results: list[EventIngestionResult]

    @property
    def success(self) -> bool:
        return self.rejected == 0 and self.accepted == self.total


def _extract_message(event: CanonicalEventBase) -> str | None:
    if isinstance(event, LogEvent):
        return event.message
    if isinstance(event, AlertEvent):
        return event.name
    if isinstance(event, MetricEvent):
        return f"{event.metric_name}={event.value}"
    if isinstance(event, DeploymentEvent):
        parts = [event.version, event.commit_sha]
        return " ".join(p for p in parts if p) or None
    if isinstance(event, TraceEvent):
        return event.operation_name
    return None


def _extract_severity(event: CanonicalEventBase) -> Severity | None:
    if isinstance(event, (LogEvent, AlertEvent)):
        return event.severity
    return None


def _build_normalized_data(event: CanonicalEventBase) -> dict[str, Any] | None:
    """Merge caller-supplied normalized data with type-specific fields."""

    payload = dict(event.normalized_data) if event.normalized_data else {}
    for key, value in event.model_dump().items():
        if key in _ENVELOPE_KEYS or value is None:
            continue
        payload[key] = value
    return payload or None


def canonical_to_event_row(
    event: CanonicalEventBase,
    *,
    project_id: int,
    service_id: int | None,
) -> EventRow:
    """Map a canonical event to a new ORM ``Event`` row (not yet persisted)."""

    return EventRow(
        project_id=project_id,
        service_id=service_id,
        event_type=event.event_type,
        source=event.source,
        source_type=event.source_type,
        source_id=event.source_id,
        timestamp=event.timestamp,
        environment=event.environment,
        severity=_extract_severity(event),
        message=_extract_message(event),
        raw_data=dict(event.raw_data),
        normalized_data=_build_normalized_data(event),
    )


class EventIngestionService:
    """Persist canonical events for a project."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._project_cache: dict[int, bool] = {}
        self._service_cache: dict[tuple[int, str], int] = {}

    async def ingest_one(
        self,
        project_id: int,
        event: CanonicalEventBase | dict[str, Any],
        *,
        index: int = 0,
    ) -> EventIngestionResult:
        batch = await self.ingest_batch(project_id, [event])
        result = batch.results[0]
        if index != result.index:
            return result.model_copy(update={"index": index})
        return result

    async def ingest_batch(
        self,
        project_id: int,
        events: Sequence[CanonicalEventBase | dict[str, Any]],
        *,
        collect_results: bool = True,
    ) -> BatchIngestionResult:
        results: list[EventIngestionResult] = []
        accepted = 0

        if not await self._project_exists(project_id):
            if collect_results:
                for index in range(len(events)):
                    results.append(
                        EventIngestionResult(
                            index=index,
                            status=IngestionStatus.PROJECT_NOT_FOUND,
                            errors=[f"project {project_id} not found"],
                        )
                    )
            return BatchIngestionResult(
                project_id=project_id,
                total=len(events),
                accepted=0,
                rejected=len(events),
                results=results,
            )

        rows: list[tuple[int, EventRow]] = []

        for index, raw in enumerate(events):
            try:
                event = self._coerce_event(raw)
            except ValidationError as exc:
                if collect_results:
                    results.append(
                        EventIngestionResult(
                            index=index,
                            status=IngestionStatus.VALIDATION_ERROR,
                            errors=[str(err) for err in exc.errors()],
                        )
                    )
                continue

            service_id: int | None = None
            if event.service:
                resolved = await self._resolve_service(project_id, event.service)
                if resolved is None:
                    if collect_results:
                        results.append(
                            EventIngestionResult(
                                index=index,
                                status=IngestionStatus.SERVICE_NOT_FOUND,
                                event_type=event.event_type.value,
                                errors=[
                                    (
                                        f"service {event.service!r} not found "
                                        f"in project {project_id}"
                                    )
                                ],
                            )
                        )
                    continue
                service_id = resolved

            row = canonical_to_event_row(
                event, project_id=project_id, service_id=service_id
            )
            rows.append((index, row))

        if rows:
            try:
                for _index, row in rows:
                    self._session.add(row)
                await self._session.flush()
            except Exception as exc:
                logger.exception(
                    "event ingestion flush failed for project %s", project_id
                )
                await self._session.rollback()
                if collect_results:
                    for index, _row in rows:
                        results.append(
                            EventIngestionResult(
                                index=index,
                                status=IngestionStatus.ERROR,
                                errors=[str(exc)],
                            )
                        )
                return BatchIngestionResult(
                    project_id=project_id,
                    total=len(events),
                    accepted=0,
                    rejected=len(events),
                    results=sorted(results, key=lambda r: r.index),
                )

            for index, row in rows:
                accepted += 1
                if collect_results:
                    results.append(
                        EventIngestionResult(
                            index=index,
                            status=IngestionStatus.ACCEPTED,
                            event_id=row.id,
                            event_type=row.event_type.value,
                            service_id=row.service_id,
                        )
                    )

        rejected = len(events) - accepted
        return BatchIngestionResult(
            project_id=project_id,
            total=len(events),
            accepted=accepted,
            rejected=rejected,
            results=sorted(results, key=lambda r: r.index) if collect_results else [],
        )

    async def ingest_batches(
        self,
        project_id: int,
        events: Iterable[CanonicalEventBase | dict[str, Any]],
        *,
        chunk_size: int = 1000,
        collect_results: bool = True,
    ) -> BatchIngestionResult:
        """Ingest events in fixed-size chunks to bound peak memory."""

        if chunk_size < 1:
            msg = "chunk_size must be >= 1"
            raise ValueError(msg)

        combined_results: list[EventIngestionResult] = []
        total = 0
        accepted = 0
        index_offset = 0
        batch: list[CanonicalEventBase | dict[str, Any]] = []

        async def _flush_batch() -> None:
            nonlocal total, accepted, index_offset, batch
            if not batch:
                return
            result = await self.ingest_batch(
                project_id,
                batch,
                collect_results=collect_results,
            )
            total += result.total
            accepted += result.accepted
            if collect_results:
                for item in result.results:
                    combined_results.append(
                        item.model_copy(update={"index": item.index + index_offset})
                    )
            index_offset += len(batch)
            batch = []

        for event in events:
            batch.append(event)
            if len(batch) >= chunk_size:
                await _flush_batch()
        await _flush_batch()

        return BatchIngestionResult(
            project_id=project_id,
            total=total,
            accepted=accepted,
            rejected=total - accepted,
            results=combined_results,
        )

    @staticmethod
    def _coerce_event(raw: CanonicalEventBase | dict[str, Any]) -> CanonicalEventBase:
        if isinstance(raw, CanonicalEventBase):
            return raw
        return parse_event(raw)

    async def _project_exists(self, project_id: int) -> bool:
        if project_id in self._project_cache:
            return self._project_cache[project_id]
        result = await self._session.execute(
            select(Project.id).where(Project.id == project_id)
        )
        exists = result.scalar_one_or_none() is not None
        self._project_cache[project_id] = exists
        return exists

    async def _resolve_service(self, project_id: int, name: str) -> int | None:
        key = (project_id, name)
        if key in self._service_cache:
            return self._service_cache[key]
        result = await self._session.execute(
            select(Service.id).where(
                Service.project_id == project_id,
                Service.name == name,
            )
        )
        service_id = result.scalar_one_or_none()
        if service_id is not None:
            self._service_cache[key] = service_id
        return service_id
