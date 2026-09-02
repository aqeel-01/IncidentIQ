"""Threshold helpers for metric anomaly detection."""

from __future__ import annotations

from app.core.config import Settings
from app.domain.anomaly.types import AnomalyThresholds


def anomaly_thresholds_from_settings(settings: Settings) -> AnomalyThresholds:
    """Build :class:`AnomalyThresholds` from application settings."""

    return AnomalyThresholds(
        window_size=settings.metric_anomaly_window_size,
        min_points=settings.metric_anomaly_min_points,
        z_score_threshold=settings.metric_anomaly_z_score_threshold,
        percentage_change_threshold=settings.metric_anomaly_percentage_change_threshold,
        percentile_low_threshold=settings.metric_anomaly_percentile_low_threshold,
        percentile_high_threshold=settings.metric_anomaly_percentile_high_threshold,
        min_stddev=settings.metric_anomaly_min_stddev,
    )
