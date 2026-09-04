"""Schemas for the RCA evaluation framework."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.rca.package import RCAEvidencePackage
from app.domain.rca.types import RCAStatus

EvalBackendName = Literal["local_small", "local_7b", "groq"]


class GoldLabel(BaseModel):
    """Known-correct labels for a synthetic benchmark incident."""

    model_config = ConfigDict(frozen=True)

    root_cause_title: str = Field(min_length=1)
    root_cause_aliases: list[str] = Field(default_factory=list)
    expected_status: RCAStatus = RCAStatus.CONFIDENT
    allow_no_root_cause: bool = False
    ranked_hypothesis_titles: list[str] = Field(default_factory=list)
    supporting_evidence_keys: list[str] = Field(default_factory=list)
    # Extra keys the model may cite without counting as hallucinations.
    valid_evidence_keys: list[str] = Field(default_factory=list)


class BenchmarkCase(BaseModel):
    """One synthetic incident with gold labels."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    package: RCAEvidencePackage
    gold: GoldLabel


class BenchmarkDataset(BaseModel):
    """Collection of synthetic RCA benchmark cases."""

    model_config = ConfigDict(frozen=True)

    name: str = "incidentiq-rca-benchmark"
    version: str = "1.0"
    cases: list[BenchmarkCase] = Field(default_factory=list)


class CaseMetricScores(BaseModel):
    """Per-case metric scores for one backend."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    backend: EvalBackendName
    accurate: bool
    primary_title: str | None = None
    primary_rank: int | None = None
    reciprocal_rank: float = Field(ge=0.0, le=1.0)
    ranking_kendall_tau: float | None = None
    grounding_precision: float | None = None
    grounding_recall: float | None = None
    grounding_f1: float | None = None
    hallucination_rate: float = Field(ge=0.0, le=1.0)
    cited_evidence_keys: list[str] = Field(default_factory=list)
    hallucinated_keys: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: str
    error: str | None = None


class CalibrationBin(BaseModel):
    """One confidence bin for calibration reporting."""

    model_config = ConfigDict(frozen=True)

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    count: int = Field(ge=0)
    mean_confidence: float | None = None
    accuracy: float | None = None


class BackendAggregateMetrics(BaseModel):
    """Aggregate metrics for one evaluation backend."""

    model_config = ConfigDict(frozen=True)

    backend: EvalBackendName
    cases_evaluated: int = Field(ge=0)
    cases_failed: int = Field(ge=0)
    rca_accuracy: float | None = None
    mean_reciprocal_rank: float | None = None
    mean_ranking_kendall_tau: float | None = None
    mean_grounding_precision: float | None = None
    mean_grounding_recall: float | None = None
    mean_grounding_f1: float | None = None
    mean_hallucination_rate: float | None = None
    expected_calibration_error: float | None = None
    mean_confidence_when_correct: float | None = None
    mean_confidence_when_incorrect: float | None = None
    calibration_bins: list[CalibrationBin] = Field(default_factory=list)
    case_scores: list[CaseMetricScores] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Machine-readable multi-backend RCA evaluation report."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    dataset_name: str
    dataset_version: str
    generated_at: datetime
    backends: list[BackendAggregateMetrics] = Field(default_factory=list)
    comparison: dict[str, dict[str, float | None]] = Field(default_factory=dict)
