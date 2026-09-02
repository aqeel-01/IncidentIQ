"""Incident domain service for creation, retrieval, and listing."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import IncidentStatus, Severity
from app.db.models.incident import Incident
from app.db.models.project import Project
from app.db.models.service import Service
from app.domain.incident_fingerprinting import (
    compute_incident_fingerprint_from_title,
    problem_identity_from_title,
)
from app.domain.normalization.fields import normalize_environment

ACTIVE_INCIDENT_STATUSES = frozenset(
    {
        IncidentStatus.OPEN,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.IDENTIFIED,
    }
)


class IncidentValidationError(ValueError):
    """Raised when incident input fails domain validation."""


class IncidentCreateAction(enum.StrEnum):
    CREATED = "CREATED"
    MERGED = "MERGED"


class IncidentResolveAction(enum.StrEnum):
    RESOLVED = "RESOLVED"


class CreateIncidentInput(BaseModel):
    """Validated input for creating an incident."""

    model_config = {"frozen": True}

    project_id: int
    title: str = Field(min_length=1, max_length=500)
    environment: str = Field(min_length=1, max_length=100)
    severity: Severity
    service_id: int | None = None
    status: IncidentStatus = IncidentStatus.OPEN
    started_at: datetime | None = None
    ended_at: datetime | None = None
    occurrence_count: int = Field(default=1, ge=1)

    @field_validator("started_at", "ended_at")
    @classmethod
    def _normalize_to_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class IncidentCreateResult:
    incident: Incident
    action: IncidentCreateAction


@dataclass(frozen=True, slots=True)
class IncidentResolveResult:
    incident: Incident
    action: IncidentResolveAction = IncidentResolveAction.RESOLVED


@dataclass(frozen=True, slots=True)
class IncidentListFilters:
    project_id: int
    page: int = 1
    page_size: int = 20
    severities: tuple[Severity, ...] | None = None
    statuses: tuple[IncidentStatus, ...] | None = None


@dataclass(frozen=True, slots=True)
class IncidentListResult:
    items: list[Incident]
    total: int
    page: int
    page_size: int


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def merge_incident_occurrence(
    *,
    occurrence_count: int,
    started_at: datetime,
    event_started_at: datetime,
) -> tuple[int, datetime]:
    """Return updated ``(occurrence_count, started_at)`` after a duplicate event."""

    started_at_utc = _to_utc(started_at)
    event_started_at_utc = _to_utc(event_started_at)
    return (
        occurrence_count + 1,
        event_started_at_utc
        if event_started_at_utc < started_at_utc
        else started_at_utc,
    )


class IncidentService:
    """Create and query incidents within a project scope."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: CreateIncidentInput) -> IncidentCreateResult:
        project = await self._session.get(Project, data.project_id)
        if project is None:
            raise LookupError(f"project {data.project_id} not found")

        if data.service_id is not None:
            service = (
                await self._session.execute(
                    select(Service).where(
                        Service.id == data.service_id,
                        Service.project_id == data.project_id,
                    )
                )
            ).scalar_one_or_none()
            if service is None:
                raise IncidentValidationError(
                    f"service {data.service_id} does not belong to project "
                    f"{data.project_id}"
                )

        started_at = data.started_at or datetime.now(UTC)
        if data.ended_at is not None and data.ended_at < started_at:
            raise IncidentValidationError("ended_at must not be before started_at")

        fingerprint = compute_incident_fingerprint_from_title(
            service_id=data.service_id,
            environment=data.environment,
            title=data.title,
        )
        existing = (
            await self._session.execute(
                select(Incident).where(
                    Incident.project_id == data.project_id,
                    Incident.fingerprint == fingerprint,
                    Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            count, earliest_started_at = merge_incident_occurrence(
                occurrence_count=existing.occurrence_count,
                started_at=existing.started_at,
                event_started_at=started_at,
            )
            existing.occurrence_count = count
            existing.started_at = earliest_started_at
            if existing.service_id is None and data.service_id is not None:
                existing.service_id = data.service_id
            await self._session.flush()
            await self._session.refresh(existing)
            return IncidentCreateResult(
                incident=existing,
                action=IncidentCreateAction.MERGED,
            )

        environment = (
            normalize_environment(data.environment) or data.environment.strip()
        )
        incident = Incident(
            project_id=data.project_id,
            service_id=data.service_id,
            title=data.title,
            environment=environment,
            fingerprint=fingerprint,
            severity=data.severity,
            status=data.status,
            started_at=started_at,
            ended_at=data.ended_at,
            occurrence_count=data.occurrence_count,
        )
        self._session.add(incident)
        await self._session.flush()
        return IncidentCreateResult(
            incident=incident,
            action=IncidentCreateAction.CREATED,
        )

    async def resolve_matching_active(
        self,
        *,
        project_id: int,
        service_id: int | None,
        environment: str,
        title: str,
        ended_at: datetime | None = None,
    ) -> IncidentResolveResult | None:
        fingerprint = compute_incident_fingerprint_from_title(
            service_id=service_id,
            environment=environment,
            title=title,
        )
        existing = (
            await self._session.execute(
                select(Incident).where(
                    Incident.project_id == project_id,
                    Incident.fingerprint == fingerprint,
                    Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            return None

        existing.status = IncidentStatus.RESOLVED
        existing.ended_at = ended_at or datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(existing)
        return IncidentResolveResult(incident=existing)

    async def get_by_id(self, incident_id: int) -> Incident | None:
        return await self._session.get(Incident, incident_id)

    async def list(self, filters: IncidentListFilters) -> IncidentListResult:
        if filters.page < 1:
            raise IncidentValidationError("page must be >= 1")
        if filters.page_size < 1:
            raise IncidentValidationError("page_size must be >= 1")

        query = select(Incident).where(Incident.project_id == filters.project_id)
        if filters.severities:
            query = query.where(Incident.severity.in_(filters.severities))
        if filters.statuses:
            query = query.where(Incident.status.in_(filters.statuses))

        count_query = (
            select(func.count())
            .select_from(Incident)
            .where(Incident.project_id == filters.project_id)
        )
        if filters.severities:
            count_query = count_query.where(Incident.severity.in_(filters.severities))
        if filters.statuses:
            count_query = count_query.where(Incident.status.in_(filters.statuses))

        total = (await self._session.execute(count_query)).scalar_one()

        offset = (filters.page - 1) * filters.page_size
        rows = (
            (
                await self._session.execute(
                    query.order_by(Incident.started_at.desc(), Incident.id.desc())
                    .offset(offset)
                    .limit(filters.page_size)
                )
            )
            .scalars()
            .all()
        )

        return IncidentListResult(
            items=list(rows),
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )


def incident_fingerprint_for_input(data: CreateIncidentInput) -> str:
    """Expose fingerprint computation for tests and downstream callers."""

    return compute_incident_fingerprint_from_title(
        service_id=data.service_id,
        environment=data.environment,
        title=data.title,
    )


def incident_problem_identity(title: str) -> str:
    """Expose normalized problem identity for tests."""

    return problem_identity_from_title(title)
