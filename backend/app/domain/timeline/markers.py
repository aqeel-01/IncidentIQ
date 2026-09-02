"""Identify key markers on an incident timeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models.enums import IncidentStatus, Severity
from app.db.models.incident import Incident
from app.domain.timeline.builders import is_anomaly_entry, is_resolved_alert
from app.domain.timeline.types import TimelineCategory, TimelineEntry, TimelineMarkers


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def identify_markers(
    entries: list[TimelineEntry],
    *,
    incident: Incident,
    deployment_lookback: timedelta = timedelta(hours=24),
) -> TimelineMarkers:
    """Identify first anomaly, error, alert, recent deployment, and recovery."""

    sorted_entries = sorted(entries, key=lambda item: item.timestamp)
    incident_start = _to_utc(incident.started_at)
    deployment_cutoff = incident_start - deployment_lookback

    first_anomaly = next(
        (entry for entry in sorted_entries if is_anomaly_entry(entry)),
        None,
    )
    first_relevant_error = next(
        (
            entry
            for entry in sorted_entries
            if entry.category is TimelineCategory.ERROR
        ),
        None,
    )
    if first_relevant_error is None:
        first_relevant_error = next(
            (
                entry
                for entry in sorted_entries
                if entry.category is TimelineCategory.LOG
                and entry.severity
                in {Severity.HIGH, Severity.CRITICAL}
            ),
            None,
        )
    first_alert = next(
        (
            entry
            for entry in sorted_entries
            if entry.category is TimelineCategory.ALERT
        ),
        None,
    )

    deployment_candidates = [
        entry
        for entry in sorted_entries
        if entry.category is TimelineCategory.DEPLOYMENT
        and deployment_cutoff <= entry.timestamp <= incident_start
    ]
    recent_deployment = (
        deployment_candidates[-1] if deployment_candidates else None
    )

    recovery = _identify_recovery(
        sorted_entries,
        incident=incident,
        first_alert=first_alert,
    )

    return TimelineMarkers(
        first_anomaly=first_anomaly,
        first_relevant_error=first_relevant_error,
        first_alert=first_alert,
        recent_deployment=recent_deployment,
        recovery=recovery,
    )


def _identify_recovery(
    entries: list[TimelineEntry],
    *,
    incident: Incident,
    first_alert: TimelineEntry | None,
) -> TimelineEntry | None:
    if incident.ended_at is not None and incident.status in {
        IncidentStatus.RESOLVED,
        IncidentStatus.CLOSED,
    }:
        return TimelineEntry(
            id=f"incident:{incident.id}:recovery",
            category=TimelineCategory.ALERT,
            timestamp=_to_utc(incident.ended_at),
            title="Incident resolved",
            summary=f"Incident marked {incident.status.value.lower()}",
            severity=None,
            metadata={"incident_status": incident.status.value},
        )

    if first_alert is None:
        return None

    resolved_alerts = [
        entry
        for entry in entries
        if is_resolved_alert(entry)
        and entry.timestamp >= first_alert.timestamp
    ]
    return resolved_alerts[0] if resolved_alerts else None
