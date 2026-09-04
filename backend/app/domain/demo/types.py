"""Result schemas for the IncidentIQ end-to-end demo."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.rca.types import RCAResult, RCAStatus


class DemoPipelineSummary(BaseModel):
    """Compact view of investigation stage completion."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    status: str
    stage: str
    stages_completed: list[str] = Field(default_factory=list)
    stage_artifacts: dict[str, Any] = Field(default_factory=dict)


class DemoTimelineSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_count: int = 0
    anomaly_count: int = 0
    correlation_count: int = 0
    deployment_correlation: str | None = None


class DemoEvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_group_id: int | None = None
    item_count: int = 0
    quality_score: int | None = None
    quality_summary: str | None = None


class DemoResult(BaseModel):
    """Machine-readable end-to-end demo output."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    scenario: str = "payments-deploy-regression"
    generated_at: datetime
    reproducible: bool = True
    deterministic_ai: bool = True
    incident_id: int
    project_id: int
    service: str
    incident_title: str
    pipeline: DemoPipelineSummary
    timeline: DemoTimelineSummary
    evidence: DemoEvidenceSummary
    rca_status: RCAStatus
    confidence: float
    evidence_quality: int
    root_cause: str | None = None
    root_cause_description: str | None = None
    root_cause_rationale: str | None = None
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    alternative_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    verification_steps: list[dict[str, Any]] = Field(default_factory=list)
    rca: RCAResult
    ai_provider: str
    ai_model: str
    engine_version: str
    prompt_version: str
