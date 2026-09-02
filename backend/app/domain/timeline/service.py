"""Timeline construction service."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.error_group import ErrorGroup
from app.db.models.event import Event
from app.db.models.incident import Incident
from app.domain.timeline.builders import (
    error_group_to_timeline_entry,
    event_to_timeline_entry,
)
from app.domain.timeline.correlation import incident_timeline_window
from app.domain.timeline.markers import identify_markers
from app.domain.timeline.types import TimelineEntry, TimelineResult


class TimelineService:
    """Build chronological incident timelines from correlated evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        markers = identify_markers(entries, incident=incident)
        counts = Counter(entry.category.value for entry in entries)

        return TimelineResult(
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

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
