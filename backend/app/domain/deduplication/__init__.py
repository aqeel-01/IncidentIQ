"""Duplicate event merging into logical error groups."""

from app.domain.deduplication.merge import merge_error_group_timestamps
from app.domain.deduplication.service import (
    ErrorGroupDeduplicationService,
    error_group_input_from_normalized,
)
from app.domain.deduplication.similarity import (
    SimilarityCandidateGroup,
    SimilarityMatch,
    SimilarityThresholds,
    classify_similarity,
    compute_message_similarity,
    find_best_similar_match,
)
from app.domain.deduplication.types import (
    ErrorGroupEventInput,
    ErrorGroupMergeResult,
    MergeAction,
    SimilarityClassification,
    SimilarityMatchSummary,
)

__all__ = [
    "ErrorGroupDeduplicationService",
    "ErrorGroupEventInput",
    "ErrorGroupMergeResult",
    "MergeAction",
    "SimilarityCandidateGroup",
    "SimilarityClassification",
    "SimilarityMatch",
    "SimilarityMatchSummary",
    "SimilarityThresholds",
    "classify_similarity",
    "compute_message_similarity",
    "error_group_input_from_normalized",
    "find_best_similar_match",
    "merge_error_group_timestamps",
]
