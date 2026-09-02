"""Process Alertmanager webhooks and drive incident lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import IncidentStatus, Severity
from app.db.models.project import Project
from app.db.models.service import Service
from app.domain.alertmanager.parse import (
    AlertmanagerParseError,
    environment_from_labels,
    incident_title_from_alert,
    parse_alertmanager_webhook,
    service_name_from_labels,
    severity_from_labels,
)
from app.domain.alertmanager.types import AlertmanagerWebhookPayload
from app.domain.events import AlertEvent, AlertStatus
from app.domain.incidents import (
    CreateIncidentInput,
    IncidentCreateAction,
    IncidentService,
)


class AlertmanagerWebhookError(ValueError):
    """Raised when webhook processing fails validation."""


@dataclass(frozen=True, slots=True)
class AlertIncidentOutcome:
    alert_name: str
    alert_status: AlertStatus
    incident_id: int | None
    action: str


@dataclass(frozen=True, slots=True)
class AlertmanagerWebhookResult:
    alerts_received: int
    incidents_created: int = 0
    incidents_merged: int = 0
    incidents_resolved: int = 0
    outcomes: list[AlertIncidentOutcome] = field(default_factory=list)


class AlertmanagerWebhookService:
    """Ingest Alertmanager payloads and create or update incidents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._incidents = IncidentService(session)

    async def ingest(
        self,
        *,
        project_id: int,
        payload: AlertmanagerWebhookPayload,
    ) -> AlertmanagerWebhookResult:
        project = await self._session.get(Project, project_id)
        if project is None:
            raise LookupError(f"project {project_id} not found")

        try:
            alert_events = parse_alertmanager_webhook(payload)
        except AlertmanagerParseError as exc:
            raise AlertmanagerWebhookError(str(exc)) from exc

        created = 0
        merged = 0
        resolved = 0
        outcomes: list[AlertIncidentOutcome] = []

        for alert_event in alert_events:
            service_id = await self._resolve_service_id(
                project_id=project_id,
                service_name=alert_event.service,
            )
            if alert_event.status is AlertStatus.FIRING:
                result = await self._incidents.create(
                    CreateIncidentInput(
                        project_id=project_id,
                        service_id=service_id,
                        title=self._incident_title(alert_event),
                        environment=alert_event.environment or "production",
                        severity=alert_event.severity or Severity.MEDIUM,
                        status=IncidentStatus.OPEN,
                        started_at=alert_event.timestamp,
                    )
                )
                if result.action is IncidentCreateAction.CREATED:
                    created += 1
                else:
                    merged += 1
                outcomes.append(
                    AlertIncidentOutcome(
                        alert_name=alert_event.name,
                        alert_status=alert_event.status,
                        incident_id=result.incident.id,
                        action=result.action.value,
                    )
                )
            else:
                resolve_result = await self._incidents.resolve_matching_active(
                    project_id=project_id,
                    service_id=service_id,
                    environment=alert_event.environment or "production",
                    title=self._incident_title(alert_event),
                    ended_at=alert_event.timestamp,
                )
                if resolve_result is not None:
                    resolved += 1
                    outcomes.append(
                        AlertIncidentOutcome(
                            alert_name=alert_event.name,
                            alert_status=alert_event.status,
                            incident_id=resolve_result.incident.id,
                            action=resolve_result.action.value,
                        )
                    )
                else:
                    outcomes.append(
                        AlertIncidentOutcome(
                            alert_name=alert_event.name,
                            alert_status=alert_event.status,
                            incident_id=None,
                            action="UNMATCHED",
                        )
                    )

        return AlertmanagerWebhookResult(
            alerts_received=len(alert_events),
            incidents_created=created,
            incidents_merged=merged,
            incidents_resolved=resolved,
            outcomes=outcomes,
        )

    async def _resolve_service_id(
        self,
        *,
        project_id: int,
        service_name: str | None,
    ) -> int | None:
        if not service_name:
            return None
        service = (
            await self._session.execute(
                select(Service).where(
                    Service.project_id == project_id,
                    Service.name == service_name,
                )
            )
        ).scalar_one_or_none()
        return service.id if service else None

    def _incident_title(self, alert_event: AlertEvent) -> str:
        return incident_title_from_alert(alert_event.labels)


def alert_labels_for_validation(labels: dict[str, str]) -> dict[str, str]:
    """Expose label helpers for unit tests."""

    return {
        "service": service_name_from_labels(labels) or "",
        "environment": environment_from_labels(labels),
        "severity": severity_from_labels(labels).value,
    }
