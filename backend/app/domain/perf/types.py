"""Types for ingestion/investigation performance benchmarks."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StageTiming(BaseModel):
    """Wall-clock and memory observations for one measured stage."""

    model_config = ConfigDict(frozen=True)

    name: str
    duration_seconds: float = Field(ge=0.0)
    peak_rss_mb: float | None = None
    python_peak_mb: float | None = None
    items_processed: int = Field(ge=0, default=0)
    items_output: int = Field(ge=0, default=0)
    notes: str | None = None


class ScaleBenchmarkResult(BaseModel):
    """Results for one event-count scale (10K / 100K / 1M)."""

    model_config = ConfigDict(frozen=True)

    event_count: int
    stages: list[StageTiming] = Field(default_factory=list)
    ingestion_seconds: float | None = None
    normalization_seconds: float | None = None
    deduplication_seconds: float | None = None
    analysis_seconds: float | None = None
    rca_seconds: float | None = None
    peak_rss_mb: float | None = None
    python_peak_mb: float | None = None
    dataset_path: str | None = None
    incremental: bool = True


class PerformanceReport(BaseModel):
    """Machine-readable multi-scale performance report."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    generated_at: datetime
    host: str
    python_version: str
    scales: list[ScaleBenchmarkResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
