"""Metric anomaly detection engine."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.anomaly.statistics import rolling_statistics
from app.domain.anomaly.types import (
    AnomalyDetectionResult,
    AnomalyEvidence,
    AnomalySignalType,
    AnomalyThresholds,
    MetricPoint,
    RollingStatistics,
)


class MetricAnomalyDetector:
    """Detect metric anomalies using rolling numerical statistics."""

    def __init__(self, thresholds: AnomalyThresholds | None = None) -> None:
        self._thresholds = thresholds or AnomalyThresholds()

    @property
    def thresholds(self) -> AnomalyThresholds:
        return self._thresholds

    def detect(self, points: Sequence[MetricPoint]) -> AnomalyDetectionResult:
        """Analyze a metric series and return structured anomaly evidence."""

        ordered = sorted(points, key=lambda point: point.timestamp)
        if not ordered:
            return AnomalyDetectionResult(
                metric_name=None,
                window_size=self._thresholds.window_size,
                total_points=0,
                anomalies=[],
                latest_statistics=None,
            )

        metric_name = ordered[0].metric_name
        values = [point.value for point in ordered]
        anomalies: list[AnomalyEvidence] = []
        latest_stats: RollingStatistics | None = None

        for index in range(len(ordered)):
            if index + 1 < self._thresholds.min_points:
                continue

            history = values[:index]
            if len(history) < self._thresholds.min_points - 1:
                continue

            current_point = ordered[index]
            previous_value = values[index - 1] if index > 0 else None
            mean, stddev, z_value, pct_rank, pct_change, moving_avg = (
                rolling_statistics(
                    history,
                    current=current_point.value,
                    window_size=self._thresholds.window_size,
                    min_stddev=self._thresholds.min_stddev,
                    previous=previous_value,
                )
            )

            latest_stats = RollingStatistics(
                window_size=min(len(history), self._thresholds.window_size),
                count=len(history),
                mean=mean,
                stddev=stddev,
                moving_average=moving_avg,
                minimum=min(history[-self._thresholds.window_size :]),
                maximum=max(history[-self._thresholds.window_size :]),
                latest_value=current_point.value,
                latest_z_score=z_value,
                latest_percentile=pct_rank,
                latest_percentage_change=pct_change,
            )

            anomalies.extend(
                self._evaluate_point(
                    current_point,
                    mean=mean,
                    stddev=stddev,
                    moving_avg=moving_avg,
                    z_value=z_value,
                    pct_rank=pct_rank,
                    pct_change=pct_change,
                )
            )

        return AnomalyDetectionResult(
            metric_name=metric_name,
            window_size=self._thresholds.window_size,
            total_points=len(ordered),
            anomalies=anomalies,
            latest_statistics=latest_stats,
        )

    def _evaluate_point(
        self,
        point: MetricPoint,
        *,
        mean: float,
        stddev: float,
        moving_avg: float,
        z_value: float,
        pct_rank: float | None,
        pct_change: float | None,
    ) -> list[AnomalyEvidence]:
        evidence: list[AnomalyEvidence] = []
        thresholds = self._thresholds
        window_size = thresholds.window_size

        if abs(z_value) >= thresholds.z_score_threshold:
            evidence.append(
                AnomalyEvidence(
                    signal_type=AnomalySignalType.Z_SCORE,
                    metric_name=point.metric_name,
                    timestamp=point.timestamp,
                    value=point.value,
                    threshold=thresholds.z_score_threshold,
                    observed=round(z_value, 6),
                    baseline_mean=round(mean, 6),
                    baseline_stddev=round(stddev, 6),
                    moving_average=round(moving_avg, 6),
                    window_size=window_size,
                    detail=(
                        f"z-score {z_value:.2f} exceeded threshold "
                        f"{thresholds.z_score_threshold:.2f}"
                    ),
                )
            )

        if (
            pct_change is not None
            and abs(pct_change) >= thresholds.percentage_change_threshold
        ):
            evidence.append(
                AnomalyEvidence(
                    signal_type=AnomalySignalType.PERCENTAGE_CHANGE,
                    metric_name=point.metric_name,
                    timestamp=point.timestamp,
                    value=point.value,
                    threshold=thresholds.percentage_change_threshold,
                    observed=round(pct_change, 6),
                    baseline_mean=round(mean, 6),
                    moving_average=round(moving_avg, 6),
                    percentage_change=round(pct_change, 6),
                    window_size=window_size,
                    detail=(
                        f"percentage change {pct_change:.2f}% exceeded threshold "
                        f"{thresholds.percentage_change_threshold:.2f}%"
                    ),
                )
            )

        if pct_rank is not None and (
            pct_rank <= thresholds.percentile_low_threshold
            or pct_rank >= thresholds.percentile_high_threshold
        ):
            threshold = (
                thresholds.percentile_low_threshold
                if pct_rank <= thresholds.percentile_low_threshold
                else thresholds.percentile_high_threshold
            )
            evidence.append(
                AnomalyEvidence(
                    signal_type=AnomalySignalType.PERCENTILE,
                    metric_name=point.metric_name,
                    timestamp=point.timestamp,
                    value=point.value,
                    threshold=threshold,
                    observed=round(pct_rank, 6),
                    baseline_mean=round(mean, 6),
                    baseline_stddev=round(stddev, 6),
                    moving_average=round(moving_avg, 6),
                    percentile_rank=round(pct_rank, 6),
                    window_size=window_size,
                    detail=(
                        f"percentile rank {pct_rank:.2f} outside "
                        f"[{thresholds.percentile_low_threshold:.2f}, "
                        f"{thresholds.percentile_high_threshold:.2f}]"
                    ),
                )
            )

        return evidence
