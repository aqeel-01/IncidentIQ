"""Structured root cause analysis models."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RCAStatus(enum.StrEnum):
    """Overall confidence level of the root cause analysis."""

    CONFIDENT = "confident"
    LOW_CONFIDENCE = "low_confidence"
    NO_CONFIDENT_ROOT_CAUSE = "no_confident_root_cause"


class Hypothesis(BaseModel):
    """A proposed explanation for an incident."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class SupportingEvidence(BaseModel):
    """Evidence that supports a hypothesis."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    source: str | None = None


class ContradictingEvidence(BaseModel):
    """Evidence that contradicts a hypothesis."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    source: str | None = None


class VerificationStep(BaseModel):
    """A recommended step to validate or disprove a hypothesis."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: int = Field(default=1, ge=1, le=5)


class ExtractedSymptom(BaseModel):
    """A symptom identified during RCA symptom analysis."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    observation: str = Field(min_length=1)
    severity: str | None = None
    service: str | None = None


class RCASymptomAnalysisResult(BaseModel):
    """Structured output from the symptom extraction stage."""

    model_config = ConfigDict(frozen=True)

    symptoms: list[ExtractedSymptom] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class RCAHypothesisSet(BaseModel):
    """Structured output from the hypothesis generation stage."""

    model_config = ConfigDict(frozen=True)

    hypotheses: list[Hypothesis] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class EvaluatedHypothesis(BaseModel):
    """A hypothesis evaluated against the supplied evidence."""

    model_config = ConfigDict(frozen=True)

    hypothesis: Hypothesis
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    contradicting_evidence: list[ContradictingEvidence] = Field(default_factory=list)
    temporal_consistency_score: float = Field(ge=0.0, le=1.0)
    dependency_consistency_score: float = Field(ge=0.0, le=1.0)


class RCAHypothesisEvaluationResult(BaseModel):
    """Structured output from the evidence evaluation stage."""

    model_config = ConfigDict(frozen=True)

    evaluations: list[EvaluatedHypothesis] = Field(default_factory=list)
    ranked_titles: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class RCAResult(BaseModel):
    """Structured output from a root cause analysis."""

    model_config = ConfigDict(frozen=True)

    status: RCAStatus
    primary_hypothesis: Hypothesis | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    contradicting_evidence: list[ContradictingEvidence] = Field(default_factory=list)
    alternative_hypotheses: list[Hypothesis] = Field(default_factory=list)
    verification_steps: list[VerificationStep] = Field(default_factory=list)
    evidence_quality: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> RCAResult:
        if (
            self.status is RCAStatus.NO_CONFIDENT_ROOT_CAUSE
            and self.primary_hypothesis is not None
        ):
            msg = (
                "primary_hypothesis must be null when status is "
                "no_confident_root_cause"
            )
            raise ValueError(msg)

        if (
            self.status is not RCAStatus.NO_CONFIDENT_ROOT_CAUSE
            and self.primary_hypothesis is None
        ):
            msg = (
                "primary_hypothesis is required unless status is "
                "no_confident_root_cause"
            )
            raise ValueError(msg)

        return self


class HistoricalRCARecord(BaseModel):
    """Persisted RCA output with investigation traceability metadata."""

    model_config = ConfigDict(frozen=True)

    id: int
    project_id: int
    incident_id: int
    investigation_job_id: str | None
    evidence_group_id: int | None
    status: RCAStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quality: int = Field(ge=0, le=100)
    ai_provider: str
    ai_model: str
    engine_version: str
    prompt_version: str
    result: RCAResult
    created_at: datetime
    updated_at: datetime
