"""Tests for metric anomaly detection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.anomaly import (
    AnomalySignalType,
    AnomalyThresholds,
    MetricAnomalyDetector,
    MetricPoint,
    anomaly_thresholds_from_settings,
    moving_average,
    percentage_change,
    percentile_rank,
    standard_deviation,
    z_score,
)


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _steady_series(
    *,
    count: int = 10,
    value: float = 100.0,
    metric_name: str = "error_rate",
) -> list[MetricPoint]:
    return [
        MetricPoint(
            timestamp=_ts(index),
            value=value,
            metric_name=metric_name,
        )
        for index in range(count)
    ]


def test_statistics_helpers_compute_expected_values() -> None:
    values = [10.0, 12.0, 11.0, 13.0, 12.0]

    assert moving_average(values) == 11.6
    assert round(standard_deviation(values), 4) == 1.1402
    assert round(z_score(16.0, 11.6, 1.1402, min_stddev=1e-9), 4) == 3.859
    assert percentage_change(150.0, 100.0) == 50.0
    assert percentile_rank(12.0, values) == 62.5


def test_thresholds_validate_percentile_bounds() -> None:
    with pytest.raises(ValidationError):
        AnomalyThresholds(
            percentile_low_threshold=90.0,
            percentile_high_threshold=10.0,
        )


def test_anomaly_thresholds_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        metric_anomaly_window_size=15,
        metric_anomaly_z_score_threshold=3.0,
    )
    thresholds = anomaly_thresholds_from_settings(settings)

    assert thresholds.window_size == 15
    assert thresholds.z_score_threshold == 3.0


def test_steady_series_produces_no_anomalies() -> None:
    detector = MetricAnomalyDetector(
        AnomalyThresholds(window_size=5, min_points=5, z_score_threshold=3.0)
    )

    result = detector.detect(_steady_series(count=12))

    assert result.total_points == 12
    assert result.anomalies == []
    assert result.latest_statistics is not None
    assert result.latest_statistics.latest_z_score is not None
    assert abs(result.latest_statistics.latest_z_score) < 1.0


def test_spike_triggers_z_score_and_percentage_change() -> None:
    points = _steady_series(count=8, value=10.0)
    points.append(
        MetricPoint(timestamp=_ts(8), value=40.0, metric_name="error_rate")
    )

    detector = MetricAnomalyDetector(
        AnomalyThresholds(
            window_size=8,
            min_points=5,
            z_score_threshold=2.0,
            percentage_change_threshold=100.0,
            percentile_low_threshold=1.0,
            percentile_high_threshold=99.0,
        )
    )
    result = detector.detect(points)

    signal_types = {item.signal_type for item in result.anomalies}
    assert AnomalySignalType.Z_SCORE in signal_types
    assert AnomalySignalType.PERCENTAGE_CHANGE in signal_types

    z_score_evidence = next(
        item
        for item in result.anomalies
        if item.signal_type is AnomalySignalType.Z_SCORE
    )
    assert z_score_evidence.metric_name == "error_rate"
    assert z_score_evidence.observed > 2.0
    assert z_score_evidence.baseline_mean is not None
    assert z_score_evidence.moving_average is not None
    assert "z-score" in z_score_evidence.detail


def test_sudden_drop_triggers_percentile_anomaly() -> None:
    points = _steady_series(count=8, value=100.0)
    points.append(
        MetricPoint(timestamp=_ts(8), value=1.0, metric_name="latency_ms")
    )

    detector = MetricAnomalyDetector(
        AnomalyThresholds(
            window_size=8,
            min_points=5,
            z_score_threshold=10.0,
            percentage_change_threshold=500.0,
            percentile_low_threshold=10.0,
            percentile_high_threshold=90.0,
        )
    )
    result = detector.detect(points)

    percentile_signals = [
        item
        for item in result.anomalies
        if item.signal_type is AnomalySignalType.PERCENTILE
    ]
    assert percentile_signals
    assert percentile_signals[0].percentile_rank is not None
    assert percentile_signals[0].percentile_rank <= 10.0


def test_insufficient_points_returns_no_anomalies() -> None:
    detector = MetricAnomalyDetector(
        AnomalyThresholds(window_size=10, min_points=8)
    )

    result = detector.detect(_steady_series(count=4))

    assert result.total_points == 4
    assert result.anomalies == []
    assert result.latest_statistics is None


def test_custom_thresholds_reduce_sensitive_detection() -> None:
    points = _steady_series(count=8, value=10.0)
    points.append(
        MetricPoint(timestamp=_ts(8), value=15.0, metric_name="error_rate")
    )

    sensitive = MetricAnomalyDetector(
        AnomalyThresholds(
            window_size=8,
            min_points=5,
            z_score_threshold=1.0,
            percentage_change_threshold=10.0,
            percentile_low_threshold=5.0,
            percentile_high_threshold=95.0,
        )
    )
    strict = MetricAnomalyDetector(
        AnomalyThresholds(
            window_size=8,
            min_points=5,
            z_score_threshold=5.0,
            percentage_change_threshold=200.0,
            percentile_low_threshold=1.0,
            percentile_high_threshold=99.0,
        )
    )

    sensitive_result = sensitive.detect(points)
    strict_result = strict.detect(points)

    assert len(sensitive_result.anomalies) > len(strict_result.anomalies)


def test_latest_statistics_include_rolling_metrics() -> None:
    points = _steady_series(count=6, value=20.0)
    points.append(
        MetricPoint(timestamp=_ts(6), value=24.0, metric_name="cpu_usage")
    )

    detector = MetricAnomalyDetector(
        AnomalyThresholds(window_size=5, min_points=5)
    )
    result = detector.detect(points)

    stats = result.latest_statistics
    assert stats is not None
    assert stats.moving_average == 20.0
    assert stats.latest_value == 24.0
    assert stats.latest_percentage_change == pytest.approx(20.0)
