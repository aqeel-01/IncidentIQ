"""Timeline construction service."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.error_group import ErrorGroup
from app.db.models.event import Event
from app.db.models.incident import Incident
from app.db.models.service import Service
from app.domain.anomaly import MetricAnomalyDetector, anomaly_thresholds_from_settings
from app.domain.correlation import (
    annotate_metric_anomalies,
    correlate_service_metric_error,
    correlate_temporal,
    correlation_thresholds_from_settings,
    deployment_correlation_thresholds_from_settings,
    evaluate_deployment_correlation,
    service_correlation_thresholds_from_settings,
)
from app.domain.correlation.types import (
    DeploymentCorrelationAssessment,
    ServiceCorrelationResult,
    TemporalCorrelation,
)
from app.domain.evidence import EvidenceService
from app.domain.evidence.types import EvidenceGroup
from app.domain.timeline.builders import (
    error_group_to_timeline_entry,
    event_to_timeline_entry,
)
from app.domain.timeline.correlation import incident_timeline_window
from app.domain.timeline.markers import identify_markers
from app.domain.timeline.types import TimelineEntry, TimelineResult

TimelineResult.model_rebuild(
    _types_namespace={
        "TemporalCorrelation": TemporalCorrelation,
        "DeploymentCorrelationAssessment": DeploymentCorrelationAssessment,
        "ServiceCorrelationResult": ServiceCorrelationResult,
        "EvidenceGroup": EvidenceGroup,
    },
)


class TimelineService:
    """Build chronological incident timelines from correlated evidence."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        anomaly_detector: MetricAnomalyDetector | None = None,
    ) -> None:
        self._session = session
        self._anomaly_detector = anomaly_detector

    async def build(self, incident_id: int) -> TimelineResult | None:
        incident = await self._session.get(Incident, incident_id)
        if incident is None:
            return None

        window = incident_timeline_window(incident)
        events = await self._fetch_events(incident, window.start, window.end)
        error_groups = await self._fetch_error_groups(
            incident,
            window.start,
            window.end,
        )

        entries = self._merge_entries(events, error_groups)
        settings = get_settings()
        anomaly_detector = self._anomaly_detector or MetricAnomalyDetector(
            anomaly_thresholds_from_settings(settings)
        )
        entries = annotate_metric_anomalies(entries, anomaly_detector)
        markers = identify_markers(entries, incident=incident)
        correlations = correlate_temporal(
            entries,
            correlation_thresholds_from_settings(settings),
        )
        affected_service = await self._resolve_service_name(incident)
        deployment_correlation = evaluate_deployment_correlation(
            incident_started_at=incident.started_at,
            affected_service=affected_service,
            markers=markers,
            correlations=correlations,
            thresholds=deployment_correlation_thresholds_from_settings(settings),
        )
        service_names = await self._load_service_names(incident.project_id)
        service_correlation = correlate_service_metric_error(
            entries,
            service_names=service_names,
            thresholds=service_correlation_thresholds_from_settings(settings),
        )
        counts = Counter(entry.category.value for entry in entries)

        timeline_without_evidence = TimelineResult(
            incident_id=incident.id,
            project_id=incident.project_id,
            started_at=self._to_utc(incident.started_at),
            ended_at=(
                self._to_utc(incident.ended_at)
                if incident.ended_at is not None
                else None
            ),
            window_start=window.start,
            window_end=window.end,
            entries=entries,
            markers=markers,
            counts=dict(sorted(counts.items())),
            correlations=correlations,
            deployment_correlation=deployment_correlation,
            service_correlation=service_correlation,
        )
        evidence_group = await EvidenceService(self._session).build_from_timeline(
            timeline_without_evidence,
            service_names=service_names,
            affected_service=affected_service,
        )

        return timeline_without_evidence.model_copy(
            update={"evidence_group": evidence_group},
        )

    async def _fetch_events(
        self,
        incident: Incident,
        window_start: datetime,
        window_end: datetime,
    ) -> list[Event]:
        filters = [
            Event.project_id == incident.project_id,
            Event.timestamp >= window_start,
            Event.timestamp <= window_end,
        ]

        if incident.environment:
            filters.append(
                or_(
                    Event.environment.is_(None),
                    Event.environment == incident.environment,
                )
            )

        if incident.service_id is not None:
            filters.append(
                or_(
                    Event.service_id.is_(None),
                    Event.service_id == incident.service_id,
                )
            )

        result = await self._session.execute(
            select(Event).where(*filters).order_by(Event.timestamp.asc())
        )
        return list(result.scalars().all())

    async def _fetch_error_groups(
        self,
        incident: Incident,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ErrorGroup]:
        filters = [
            ErrorGroup.project_id == incident.project_id,
            ErrorGroup.first_seen <= window_end,
            ErrorGroup.last_seen >= window_start,
        ]

        if incident.service_id is not None:
            filters.append(
                or_(
                    ErrorGroup.service_id.is_(None),
                    ErrorGroup.service_id == incident.service_id,
                )
            )

        result = await self._session.execute(
            select(ErrorGroup).where(*filters).order_by(ErrorGroup.first_seen.asc())
        )
        return list(result.scalars().all())

    def _merge_entries(
        self,
        events: list[Event],
        error_groups: list[ErrorGroup],
    ) -> list[TimelineEntry]:
        entries: list[TimelineEntry] = []
        seen_error_group_ids: set[int] = set()

        for row in events:
            entry = event_to_timeline_entry(row)
            entries.append(entry)
            if entry.error_group_id is not None:
                seen_error_group_ids.add(entry.error_group_id)

        for group in error_groups:
            if group.id in seen_error_group_ids:
                continue
            entries.append(error_group_to_timeline_entry(group))

        entries.sort(key=lambda item: (item.timestamp, item.id))
        return entries

    async def _resolve_service_name(self, incident: Incident) -> str | None:
        if incident.service_id is None:
            return None
        service = await self._session.get(Service, incident.service_id)
        return service.name if service is not None else None

    async def _load_service_names(self, project_id: int) -> dict[int, str]:
        result = await self._session.execute(
            select(Service).where(Service.project_id == project_id)
        )
        return {service.id: service.name for service in result.scalars().all()}

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
