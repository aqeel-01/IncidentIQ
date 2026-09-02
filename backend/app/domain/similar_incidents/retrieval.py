"""Retrieve similar historical incidents for investigation context."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import IncidentStatus
from app.db.models.incident import Incident
from app.db.models.rca_result import RCAResultRecord
from app.domain.incident_fingerprinting import problem_identity_from_title
from app.domain.rca.package import RCAHistoricalContext, SimilarIncidentContext
from app.domain.similar_incidents.config import SimilarIncidentRetrievalConfig
from app.domain.similar_incidents.scoring import (
    HISTORICAL_CONTEXT_DISCLAIMER,
    build_embedding_text,
    rank_similar_incidents,
)
from app.domain.similar_incidents.types import (
    IncidentSimilarityProfile,
    SimilarIncidentMatch,
)
from app.domain.timeline.types import TimelineCategory, TimelineResult

HISTORICAL_INCIDENT_STATUSES = frozenset(
    {
        IncidentStatus.IDENTIFIED,
        IncidentStatus.RESOLVED,
        IncidentStatus.CLOSED,
    }
)

class SimilarIncidentRetrievalService:
    """Find historically similar incidents within a project."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        config: SimilarIncidentRetrievalConfig,
    ) -> None:
        self._session = session
        self._config = config

    async def find_similar(
        self,
        *,
        incident: Incident,
        timeline: TimelineResult,
        service_names: dict[int, str] | None = None,
    ) -> list[SimilarIncidentMatch]:
        source = self._profile_from_incident(
            incident,
            timeline=timeline,
            service_names=service_names or {},
        )
        candidates = await self._load_candidate_profiles(
            incident,
            service_names=service_names or {},
        )
        return rank_similar_incidents(source, candidates, config=self._config)

    async def build_historical_context(
        self,
        *,
        incident: Incident,
        timeline: TimelineResult,
        service_names: dict[int, str] | None = None,
    ) -> RCAHistoricalContext | None:
        matches = await self.find_similar(
            incident=incident,
            timeline=timeline,
            service_names=service_names,
        )
        if not matches:
            return None
        return _to_historical_context(matches)

    async def _load_candidate_profiles(
        self,
        incident: Incident,
        *,
        service_names: dict[int, str],
    ) -> list[IncidentSimilarityProfile]:
        result = await self._session.execute(
            select(Incident)
            .where(
                Incident.project_id == incident.project_id,
                Incident.id != incident.id,
                Incident.status.in_(tuple(HISTORICAL_INCIDENT_STATUSES)),
            )
            .order_by(Incident.started_at.desc())
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return []

        candidate_ids = [row.id for row in candidates]
        rca_by_incident = await self._load_latest_rca_hypotheses(candidate_ids)

        profiles: list[IncidentSimilarityProfile] = []
        for candidate in candidates:
            hypothesis = rca_by_incident.get(candidate.id)
            profiles.append(
                _profile_from_incident_row(
                    candidate,
                    service_names=service_names,
                    primary_hypothesis_title=hypothesis,
                )
            )
        return profiles

    async def _load_latest_rca_hypotheses(
        self,
        incident_ids: list[int],
    ) -> dict[int, str | None]:
        if not incident_ids:
            return {}

        result = await self._session.execute(
            select(RCAResultRecord)
            .where(RCAResultRecord.incident_id.in_(incident_ids))
            .order_by(
                RCAResultRecord.incident_id.asc(),
                RCAResultRecord.created_at.desc(),
            )
        )

        hypotheses: dict[int, str | None] = {}
        for row in result.scalars().all():
            if row.incident_id in hypotheses:
                continue
            primary = row.result_data.get("primary_hypothesis")
            title = None
            if isinstance(primary, dict):
                value = primary.get("title")
                if isinstance(value, str) and value:
                    title = value
            hypotheses[row.incident_id] = title
        return hypotheses

    def _profile_from_incident(
        self,
        incident: Incident,
        *,
        timeline: TimelineResult,
        service_names: dict[int, str],
    ) -> IncidentSimilarityProfile:
        error_group_titles = _timeline_error_group_titles(timeline)
        symptom_titles = _timeline_symptom_titles(timeline)
        service_name = (
            service_names.get(incident.service_id)
            if incident.service_id is not None
            else None
        )
        problem_identity = problem_identity_from_title(incident.title)
        return IncidentSimilarityProfile(
            incident_id=incident.id,
            project_id=incident.project_id,
            title=incident.title,
            problem_identity=problem_identity,
            fingerprint=incident.fingerprint,
            environment=incident.environment,
            service_id=incident.service_id,
            service_name=service_name,
            severity=incident.severity.value,
            status=incident.status.value,
            started_at=incident.started_at,
            error_group_titles=error_group_titles,
            symptom_titles=symptom_titles,
            embedding_text=build_embedding_text(
                title=incident.title,
                problem_identity=problem_identity,
                environment=incident.environment,
                service_name=service_name,
                error_group_titles=error_group_titles,
                symptom_titles=symptom_titles,
                primary_hypothesis_title=None,
            ),
        )


def _profile_from_incident_row(
    incident: Incident,
    *,
    service_names: dict[int, str],
    primary_hypothesis_title: str | None,
) -> IncidentSimilarityProfile:
    service_name = (
        service_names.get(incident.service_id)
        if incident.service_id is not None
        else None
    )
    problem_identity = problem_identity_from_title(incident.title)
    return IncidentSimilarityProfile(
        incident_id=incident.id,
        project_id=incident.project_id,
        title=incident.title,
        problem_identity=problem_identity,
        fingerprint=incident.fingerprint,
        environment=incident.environment,
        service_id=incident.service_id,
        service_name=service_name,
        severity=incident.severity.value,
        status=incident.status.value,
        started_at=incident.started_at,
        primary_hypothesis_title=primary_hypothesis_title,
        embedding_text=build_embedding_text(
            title=incident.title,
            problem_identity=problem_identity,
            environment=incident.environment,
            service_name=service_name,
            error_group_titles=[],
            symptom_titles=[],
            primary_hypothesis_title=primary_hypothesis_title,
        ),
    )


def _timeline_error_group_titles(timeline: TimelineResult) -> list[str]:
    titles: list[str] = []
    for entry in timeline.entries:
        if entry.category is TimelineCategory.ERROR:
            titles.append(entry.title)
    return titles


def _timeline_symptom_titles(timeline: TimelineResult) -> list[str]:
    titles: list[str] = []
    for entry in timeline.entries:
        if entry.category in {TimelineCategory.LOG, TimelineCategory.ALERT}:
            titles.append(entry.title)
    return titles


def _to_historical_context(matches: list[SimilarIncidentMatch]) -> RCAHistoricalContext:
    notes = [HISTORICAL_CONTEXT_DISCLAIMER]
    for match in matches:
        summary = (
            f"Incident {match.incident_id} ({match.title}) scored "
            f"{match.similarity_score:.2f} similarity"
        )
        if match.primary_hypothesis_title:
            summary += f"; prior RCA hypothesis: {match.primary_hypothesis_title}"
        notes.append(summary)

    return RCAHistoricalContext(
        prior_incident_count=len(matches),
        related_incident_ids=[match.incident_id for match in matches],
        similar_incidents=[
            SimilarIncidentContext(
                incident_id=match.incident_id,
                title=match.title,
                similarity_score=match.similarity_score,
                environment=match.environment,
                service=match.service,
                status=match.status,
                started_at=match.started_at,
                primary_hypothesis_title=match.primary_hypothesis_title,
                matching_signals=match.matching_signals,
                context_only=True,
            )
            for match in matches
        ],
        notes=notes,
    )
