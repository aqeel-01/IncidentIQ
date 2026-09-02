"""Normalized-message similarity scoring for error-group matching."""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher

from pydantic import BaseModel, Field, model_validator

from app.domain.deduplication.types import SimilarityClassification


class SimilarityThresholds(BaseModel):
    """Configurable bounds for classifying message similarity."""

    model_config = {"frozen": True}

    high_confidence_min: float = Field(default=0.92, ge=0.0, le=1.0)
    possible_match_min: float = Field(default=0.75, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _high_confidence_above_possible(self) -> SimilarityThresholds:
        if self.high_confidence_min <= self.possible_match_min:
            msg = "high_confidence_min must be greater than possible_match_min"
            raise ValueError(msg)
        return self


class SimilarityCandidateGroup(BaseModel):
    """Existing error group compared during similarity lookup."""

    model_config = {"frozen": True}

    error_group_id: int
    normalized_message: str
    service_id: int | None = None


class SimilarityMatch(BaseModel):
    """A scored similarity result against an existing error group."""

    model_config = {"frozen": True}

    error_group_id: int
    normalized_message: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    classification: SimilarityClassification


def compute_message_similarity(left: str, right: str) -> float:
    """Return a ratio in ``[0.0, 1.0]`` between two normalized messages."""

    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left.casefold(), right.casefold()).ratio()


def classify_similarity(
    score: float,
    thresholds: SimilarityThresholds,
) -> SimilarityClassification:
    """Map a similarity score to a merge/investigation classification."""

    if score >= thresholds.high_confidence_min:
        return SimilarityClassification.HIGH_CONFIDENCE
    if score >= thresholds.possible_match_min:
        return SimilarityClassification.POSSIBLE_MATCH
    return SimilarityClassification.NO_MATCH


def _service_scope_matches(
    event_service_id: int | None,
    group_service_id: int | None,
) -> bool:
    if event_service_id is None or group_service_id is None:
        return True
    return event_service_id == group_service_id


def similarity_thresholds_from_settings(
    *,
    high_confidence_min: float,
    possible_match_min: float,
) -> SimilarityThresholds:
    """Build validated thresholds from application configuration."""

    return SimilarityThresholds(
        high_confidence_min=high_confidence_min,
        possible_match_min=possible_match_min,
    )


def find_best_similar_match(
    *,
    normalized_message: str,
    candidates: Sequence[SimilarityCandidateGroup],
    thresholds: SimilarityThresholds,
    event_service_id: int | None = None,
) -> SimilarityMatch | None:
    """Return the strongest similarity match above the possible-match floor."""

    best: SimilarityMatch | None = None
    for group in candidates:
        if not _service_scope_matches(event_service_id, group.service_id):
            continue

        score = compute_message_similarity(normalized_message, group.normalized_message)
        classification = classify_similarity(score, thresholds)
        if classification is SimilarityClassification.NO_MATCH:
            continue

        match = SimilarityMatch(
            error_group_id=group.error_group_id,
            normalized_message=group.normalized_message,
            similarity_score=score,
            classification=classification,
        )
        if best is None or score > best.similarity_score:
            best = match

    return best
