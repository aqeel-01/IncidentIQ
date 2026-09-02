"""Metric anomaly detection types."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnomalySignalType(enum.StrEnum):
    """Statistical signal that contributed to anomaly detection."""

    Z_SCORE = "z_score"
    PERCENTAGE_CHANGE = "percentage_change"
    PERCENTILE = "percentile"


class MetricPoint(BaseModel):
    """A single metric observation in a time series."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    value: float
    metric_name: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class AnomalyThresholds(BaseModel):
    """Configurable thresholds for metric anomaly detection."""

    model_config = ConfigDict(frozen=True)

    window_size: int = Field(default=20, ge=2, le=10_000)
    min_points: int = Field(default=5, ge=2, le=10_000)
    z_score_threshold: float = Field(default=2.5, gt=0)
    percentage_change_threshold: float = Field(default=50.0, ge=0)
    percentile_low_threshold: float = Field(default=5.0, ge=0, le=100)
    percentile_high_threshold: float = Field(default=95.0, ge=0, le=100)
    min_stddev: float = Field(default=1e-9, gt=0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> AnomalyThresholds:
        if self.min_points > self.window_size:
            msg = "min_points must be <= window_size"
            raise ValueError(msg)
        if self.percentile_low_threshold >= self.percentile_high_threshold:
            msg = "percentile_low_threshold must be < percentile_high_threshold"
            raise ValueError(msg)
        return self


class RollingStatistics(BaseModel):
    """Rolling-window descriptive statistics for a metric series."""

    model_config = ConfigDict(frozen=True)

    window_size: int
    count: int
    mean: float
    stddev: float
    moving_average: float
    minimum: float
    maximum: float
    latest_value: float
    latest_z_score: float | None = None
    latest_percentile: float | None = None
    latest_percentage_change: float | None = None


class AnomalyEvidence(BaseModel):
    """Structured evidence for a detected metric anomaly."""

    model_config = ConfigDict(frozen=True)

    signal_type: AnomalySignalType
    metric_name: str | None
    timestamp: datetime
    value: float
    threshold: float
    observed: float
    baseline_mean: float | None = None
    baseline_stddev: float | None = None
    moving_average: float | None = None
    percentile_rank: float | None = None
    percentage_change: float | None = None
    window_size: int
    detail: str


class AnomalyDetectionResult(BaseModel):
    """Outcome of analyzing a metric time series."""

    model_config = ConfigDict(frozen=True)

    metric_name: str | None
    window_size: int
    total_points: int
    anomalies: list[AnomalyEvidence]
    latest_statistics: RollingStatistics | None = None
