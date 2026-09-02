"""Tests for RCA domain schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.rca import (
    ContradictingEvidence,
    Hypothesis,
    RCAResult,
    RCAStatus,
    SupportingEvidence,
    VerificationStep,
)


def _hypothesis(
    *,
    title: str = "Deployment regression",
    confidence: float = 0.82,
) -> Hypothesis:
    return Hypothesis(
        title=title,
        description="Recent deployment preceded the first error spike.",
        confidence=confidence,
        rationale="Temporal correlation between deployment and errors.",
    )


def _confident_result(**overrides) -> RCAResult:
    base = {
        "status": RCAStatus.CONFIDENT,
        "primary_hypothesis": _hypothesis(),
        "confidence": 0.82,
        "supporting_evidence": [
            SupportingEvidence(
                key="marker-recent_deployment-1",
                description="Deployment preceded first error",
                confidence=0.8,
                source="timeline_marker",
            )
        ],
        "contradicting_evidence": [],
        "alternative_hypotheses": [
            Hypothesis(
                title="Upstream dependency failure",
                description="Auth service errors propagated downstream.",
                confidence=0.35,
            )
        ],
        "verification_steps": [
            VerificationStep(
                title="Compare error rate before and after deployment",
                description=(
                    "Check whether error rate increased immediately after deploy."
                ),
                priority=1,
            )
        ],
        "evidence_quality": 84,
    }
    base.update(overrides)
    return RCAResult(**base)


def test_rca_result_supports_confident_status() -> None:
    result = _confident_result()

    assert result.status is RCAStatus.CONFIDENT
    assert result.primary_hypothesis is not None
    assert result.primary_hypothesis.title == "Deployment regression"
    assert result.confidence == 0.82
    assert len(result.supporting_evidence) == 1
    assert len(result.alternative_hypotheses) == 1
    assert len(result.verification_steps) == 1
    assert result.evidence_quality == 84


def test_rca_result_supports_low_confidence_status() -> None:
    result = _confident_result(
        status=RCAStatus.LOW_CONFIDENCE,
        confidence=0.45,
        primary_hypothesis=_hypothesis(confidence=0.45),
    )

    assert result.status is RCAStatus.LOW_CONFIDENCE
    assert result.primary_hypothesis is not None
    assert result.confidence == 0.45


def test_rca_result_supports_no_confident_root_cause_status() -> None:
    result = RCAResult(
        status=RCAStatus.NO_CONFIDENT_ROOT_CAUSE,
        primary_hypothesis=None,
        confidence=0.0,
        supporting_evidence=[
            SupportingEvidence(
                key="marker-first_relevant_error-1",
                description="Errors observed but no causal chain identified",
                confidence=0.4,
            )
        ],
        contradicting_evidence=[
            ContradictingEvidence(
                key="deployment-contradict-1",
                description="Deployment alone is insufficient",
                confidence=0.3,
                source="deployment_correlation",
            )
        ],
        verification_steps=[
            VerificationStep(
                title="Collect additional service traces",
                description="Gather traces around the first error window.",
                priority=2,
            )
        ],
        evidence_quality=38,
    )

    assert result.status is RCAStatus.NO_CONFIDENT_ROOT_CAUSE
    assert result.primary_hypothesis is None
    assert result.contradicting_evidence


def test_rca_result_rejects_primary_hypothesis_for_no_confident_status() -> None:
    with pytest.raises(ValidationError, match="primary_hypothesis must be null"):
        _confident_result(
            status=RCAStatus.NO_CONFIDENT_ROOT_CAUSE,
            primary_hypothesis=_hypothesis(),
        )


def test_rca_result_requires_primary_hypothesis_for_confident_status() -> None:
    with pytest.raises(ValidationError, match="primary_hypothesis is required"):
        _confident_result(primary_hypothesis=None)


def test_hypothesis_requires_title_and_description() -> None:
    with pytest.raises(ValidationError):
        Hypothesis(title="", description="missing title", confidence=0.5)


def test_supporting_and_contradicting_evidence_validate_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        SupportingEvidence(
            key="ev-1",
            description="invalid confidence",
            confidence=1.5,
        )

    with pytest.raises(ValidationError):
        ContradictingEvidence(
            key="ev-2",
            description="invalid confidence",
            confidence=-0.1,
        )


def test_verification_step_validates_priority_bounds() -> None:
    with pytest.raises(ValidationError):
        VerificationStep(
            title="Check logs",
            description="Inspect application logs",
            priority=0,
        )

    with pytest.raises(ValidationError):
        VerificationStep(
            title="Check logs",
            description="Inspect application logs",
            priority=6,
        )


def test_rca_result_validates_evidence_quality_bounds() -> None:
    with pytest.raises(ValidationError):
        _confident_result(evidence_quality=101)

    with pytest.raises(ValidationError):
        _confident_result(evidence_quality=-1)


def test_rca_result_models_are_frozen() -> None:
    result = _confident_result()

    with pytest.raises(ValidationError):
        result.confidence = 0.5  # type: ignore[misc]
