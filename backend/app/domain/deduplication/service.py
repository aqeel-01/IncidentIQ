"""Persisted error-group deduplication service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import Severity
from app.db.models.error_group import ErrorGroup
from app.db.models.error_group_similarity_candidate import ErrorGroupSimilarityCandidate
from app.domain.deduplication.merge import merge_error_group_timestamps
from app.domain.deduplication.similarity import (
    SimilarityCandidateGroup,
    SimilarityMatch,
    SimilarityThresholds,
    find_best_similar_match,
)
from app.domain.deduplication.types import (
    ErrorGroupEventInput,
    ErrorGroupMergeResult,
    MergeAction,
    SimilarityClassification,
    SimilarityMatchSummary,
)
from app.domain.fingerprinting import compute_logical_error_fingerprint
from app.domain.normalization.types import NormalizedLogRecord


class ErrorGroupDeduplicationService:
    """Merge duplicate and high-confidence similar events into error groups."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        similarity_thresholds: SimilarityThresholds | None = None,
    ) -> None:
        self._session = session
        self._similarity_thresholds = similarity_thresholds or SimilarityThresholds()

    async def merge(self, event: ErrorGroupEventInput) -> ErrorGroupMergeResult:
        fingerprint = compute_logical_error_fingerprint(
            event_type=event.event_type,
            service=event.service,
            severity=event.severity,
            normalized_message=event.normalized_message,
        )

        existing = (
            await self._session.execute(
                select(ErrorGroup).where(
                    ErrorGroup.project_id == event.project_id,
                    ErrorGroup.fingerprint == fingerprint,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            return await self._merge_into_group(
                event,
                existing,
                fingerprint=fingerprint,
            )

        similar_match = await self._find_best_similar_match(event)
        if (
            similar_match is not None
            and similar_match.classification is SimilarityClassification.HIGH_CONFIDENCE
        ):
            target = await self._session.get(ErrorGroup, similar_match.error_group_id)
            if target is not None:
                return await self._merge_into_group(
                    event,
                    target,
                    fingerprint=fingerprint,
                    similarity_match=similar_match,
                )

        created = await self._create_group(event, fingerprint=fingerprint)
        investigation_candidate: SimilarityMatchSummary | None = None
        if (
            similar_match is not None
            and similar_match.classification is SimilarityClassification.POSSIBLE_MATCH
        ):
            await self._persist_investigation_candidate(
                project_id=event.project_id,
                source_error_group_id=created.error_group_id,
                similar_match=similar_match,
            )
            investigation_candidate = _to_match_summary(similar_match)

        return created.model_copy(
            update={"investigation_candidate": investigation_candidate}
        )

    async def _find_best_similar_match(
        self,
        event: ErrorGroupEventInput,
    ) -> SimilarityMatch | None:
        groups = (
            (
                await self._session.execute(
                    select(ErrorGroup).where(
                        ErrorGroup.project_id == event.project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        candidates = [
            SimilarityCandidateGroup(
                error_group_id=group.id,
                normalized_message=group.normalized_message,
                service_id=group.service_id,
            )
            for group in groups
        ]
        return find_best_similar_match(
            normalized_message=event.normalized_message,
            candidates=candidates,
            thresholds=self._similarity_thresholds,
            event_service_id=event.service_id,
        )

    async def _create_group(
        self,
        event: ErrorGroupEventInput,
        *,
        fingerprint: str,
    ) -> ErrorGroupMergeResult:
        group = ErrorGroup(
            project_id=event.project_id,
            service_id=event.service_id,
            fingerprint=fingerprint,
            normalized_message=event.normalized_message,
            occurrence_count=1,
            first_seen=event.timestamp,
            last_seen=event.timestamp,
            severity=event.severity,
        )
        self._session.add(group)
        await self._session.flush()
        return ErrorGroupMergeResult(
            action=MergeAction.CREATED,
            error_group_id=group.id,
            fingerprint=fingerprint,
            occurrence_count=group.occurrence_count,
            first_seen=group.first_seen,
            last_seen=group.last_seen,
        )

    async def _merge_into_group(
        self,
        event: ErrorGroupEventInput,
        existing: ErrorGroup,
        *,
        fingerprint: str,
        similarity_match: SimilarityMatch | None = None,
    ) -> ErrorGroupMergeResult:
        count, first_seen, last_seen = merge_error_group_timestamps(
            occurrence_count=existing.occurrence_count,
            first_seen=existing.first_seen,
            last_seen=existing.last_seen,
            event_timestamp=event.timestamp,
        )
        existing.occurrence_count = count
        existing.first_seen = first_seen
        existing.last_seen = last_seen
        if existing.service_id is None and event.service_id is not None:
            existing.service_id = event.service_id

        await self._session.flush()
        return ErrorGroupMergeResult(
            action=MergeAction.MERGED,
            error_group_id=existing.id,
            fingerprint=fingerprint,
            occurrence_count=existing.occurrence_count,
            first_seen=existing.first_seen,
            last_seen=existing.last_seen,
            similarity_match=(
                _to_match_summary(similarity_match) if similarity_match else None
            ),
        )

    async def _persist_investigation_candidate(
        self,
        *,
        project_id: int,
        source_error_group_id: int,
        similar_match: SimilarityMatch,
    ) -> None:
        self._session.add(
            ErrorGroupSimilarityCandidate(
                project_id=project_id,
                source_error_group_id=source_error_group_id,
                candidate_error_group_id=similar_match.error_group_id,
                similarity_score=similar_match.similarity_score,
            )
        )
        await self._session.flush()


def _to_match_summary(match: SimilarityMatch) -> SimilarityMatchSummary:
    return SimilarityMatchSummary(
        matched_error_group_id=match.error_group_id,
        normalized_message=match.normalized_message,
        similarity_score=match.similarity_score,
        classification=match.classification,
    )


def error_group_input_from_normalized(
    record: NormalizedLogRecord,
    *,
    project_id: int,
    source: str,
    service_id: int | None = None,
) -> ErrorGroupEventInput:
    """Build a merge input from a normalized log record."""

    normalized_message = record.normalized_message
    if not normalized_message and record.normalized_data:
        value = record.normalized_data.get("normalized_message")
        if isinstance(value, str):
            normalized_message = value
    if not normalized_message:
        raise ValueError("normalized_message is required for error-group merging")
    if record.timestamp is None:
        raise ValueError("timestamp is required for error-group merging")

    return ErrorGroupEventInput(
        project_id=project_id,
        timestamp=record.timestamp,
        severity=record.severity or Severity.MEDIUM,
        normalized_message=normalized_message,
        service_id=service_id,
        service=record.service,
        source=source,
    )
