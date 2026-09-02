"""Temporal correlation engine."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import timedelta

from app.db.models.enums import Severity
from app.domain.anomaly.detector import MetricAnomalyDetector
from app.domain.anomaly.types import MetricPoint
from app.domain.correlation.types import (
    CorrelationKind,
    CorrelationThresholds,
    TemporalCorrelation,
)
from app.domain.timeline.builders import is_resolved_alert
from app.domain.timeline.types import TimelineCategory, TimelineEntry


def correlation_score(lag: timedelta, *, max_lag: timedelta) -> float:
    """Score a temporal link from 0 to 1 based on proximity within ``max_lag``."""

    if lag.total_seconds() < 0 or max_lag.total_seconds() <= 0:
        return 0.0
    if lag > max_lag:
        return 0.0
    return max(0.0, 1.0 - (lag.total_seconds() / max_lag.total_seconds()))


def is_error_entry(entry: TimelineEntry) -> bool:
    """Return whether an entry represents an error signal."""

    if entry.category is TimelineCategory.ERROR:
        return True
    if entry.category is not TimelineCategory.LOG:
        return False
    if entry.severity is None:
        return False
    return entry.severity in {Severity.HIGH, Severity.CRITICAL}


def is_metric_anomaly_entry(entry: TimelineEntry) -> bool:
    """Return whether a metric entry was flagged as anomalous."""

    if entry.category is not TimelineCategory.METRIC:
        return False
    return bool(entry.metadata.get("anomaly"))


def annotate_metric_anomalies(
    entries: Sequence[TimelineEntry],
    detector: MetricAnomalyDetector | None = None,
) -> list[TimelineEntry]:
    """Run metric anomaly detection and annotate matching timeline entries."""

    metric_detector = detector or MetricAnomalyDetector()
    metric_entries = [
        entry for entry in entries if entry.category is TimelineCategory.METRIC
    ]
    if not metric_entries:
        return list(entries)

    grouped: dict[str, list[TimelineEntry]] = defaultdict(list)
    for entry in metric_entries:
        normalized = entry.metadata.get("normalized_data", {})
        metric_name = normalized.get("metric_name") or entry.title
        grouped[str(metric_name)].append(entry)

    anomaly_timestamps: set[tuple[str, object]] = set()
    for metric_name, group in grouped.items():
        points = [
            MetricPoint(
                timestamp=entry.timestamp,
                value=float(normalized.get("value", 0.0)),
                metric_name=metric_name,
            )
            for entry in group
            if (normalized := entry.metadata.get("normalized_data", {}))
            and normalized.get("value") is not None
        ]
        if not points:
            continue

        result = metric_detector.detect(points)
        for evidence in result.anomalies:
            anomaly_timestamps.add((metric_name, evidence.timestamp))

    annotated: list[TimelineEntry] = []
    for entry in entries:
        if entry.category is not TimelineCategory.METRIC:
            annotated.append(entry)
            continue

        normalized = entry.metadata.get("normalized_data", {})
        metric_name = str(normalized.get("metric_name") or entry.title)
        is_anomaly = (metric_name, entry.timestamp) in anomaly_timestamps
        if not is_anomaly:
            annotated.append(entry)
            continue

        metadata = dict(entry.metadata)
        metadata["anomaly"] = True
        annotated.append(entry.model_copy(update={"metadata": metadata}))

    return annotated


def correlate_temporal(
    entries: Sequence[TimelineEntry],
    thresholds: CorrelationThresholds | None = None,
) -> list[TemporalCorrelation]:
    """Find deterministic temporal links between incident timeline entries."""

    config = thresholds or CorrelationThresholds()
    sorted_entries = sorted(entries, key=lambda item: (item.timestamp, item.id))
    correlations: list[TemporalCorrelation] = []

    correlations.extend(
        _correlate_sources_to_targets(
            sources=_deployment_sources(sorted_entries),
            targets=_error_targets(sorted_entries),
            kind=CorrelationKind.DEPLOYMENT_TO_ERROR,
            max_lag=config.deployment_to_error_max_lag,
            min_score=config.min_score,
            reason_builder=_deployment_to_error_reason,
        )
    )
    correlations.extend(
        _correlate_sources_to_targets(
            sources=_metric_anomaly_sources(sorted_entries),
            targets=_error_targets(sorted_entries),
            kind=CorrelationKind.METRIC_ANOMALY_TO_ERROR,
            max_lag=config.metric_anomaly_to_error_max_lag,
            min_score=config.min_score,
            reason_builder=_metric_anomaly_to_error_reason,
        )
    )
    correlations.extend(
        _correlate_sources_to_targets(
            sources=_error_targets(sorted_entries),
            targets=_alert_targets(sorted_entries),
            kind=CorrelationKind.ERROR_TO_ALERT,
            max_lag=config.error_to_alert_max_lag,
            min_score=config.min_score,
            reason_builder=_error_to_alert_reason,
        )
    )

    return sorted(
        correlations,
        key=lambda item: (
            item.source.timestamp,
            item.target.timestamp,
            -item.correlation_score,
            item.kind.value,
        ),
    )


def _deployment_sources(entries: Sequence[TimelineEntry]) -> list[TimelineEntry]:
    return [
        entry
        for entry in entries
        if entry.category is TimelineCategory.DEPLOYMENT
    ]


def _metric_anomaly_sources(entries: Sequence[TimelineEntry]) -> list[TimelineEntry]:
    return [entry for entry in entries if is_metric_anomaly_entry(entry)]


def _error_targets(entries: Sequence[TimelineEntry]) -> list[TimelineEntry]:
    return [entry for entry in entries if is_error_entry(entry)]


def _alert_targets(entries: Sequence[TimelineEntry]) -> list[TimelineEntry]:
    return [
        entry
        for entry in entries
        if entry.category is TimelineCategory.ALERT and not is_resolved_alert(entry)
    ]


def _correlate_sources_to_targets(
    *,
    sources: Sequence[TimelineEntry],
    targets: Sequence[TimelineEntry],
    kind: CorrelationKind,
    max_lag: timedelta,
    min_score: float,
    reason_builder: Callable[[TimelineEntry, TimelineEntry, timedelta], str],
) -> list[TemporalCorrelation]:
    correlations: list[TemporalCorrelation] = []
    for source in sources:
        match = _find_earliest_target(source, targets, max_lag=max_lag)
        if match is None:
            continue

        target, lag = match
        score = correlation_score(lag, max_lag=max_lag)
        if score < min_score:
            continue

        correlations.append(
            TemporalCorrelation(
                kind=kind,
                source=source,
                target=target,
                time_difference=lag,
                correlation_score=round(score, 6),
                reason=reason_builder(source, target, lag),
            )
        )

    return correlations


def _find_earliest_target(
    source: TimelineEntry,
    targets: Sequence[TimelineEntry],
    *,
    max_lag: timedelta,
) -> tuple[TimelineEntry, timedelta] | None:
    best: tuple[TimelineEntry, timedelta] | None = None
    for target in targets:
        if target.id == source.id:
            continue
        lag = target.timestamp - source.timestamp
        if lag.total_seconds() <= 0 or lag > max_lag:
            continue
        if best is None or lag < best[1]:
            best = (target, lag)
    return best


def _format_duration(lag: timedelta) -> str:
    total_seconds = int(lag.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} seconds"
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        if seconds:
            return f"{minutes} minutes {seconds} seconds"
        return f"{minutes} minutes"
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return f"{hours} hours {minutes} minutes"
    return f"{hours} hours"


def _deployment_to_error_reason(
    source: TimelineEntry,
    target: TimelineEntry,
    lag: timedelta,
) -> str:
    return (
        f"Deployment '{source.title}' preceded error '{target.title}' by "
        f"{_format_duration(lag)}"
    )


def _metric_anomaly_to_error_reason(
    source: TimelineEntry,
    target: TimelineEntry,
    lag: timedelta,
) -> str:
    normalized = source.metadata.get("normalized_data", {})
    metric_name = normalized.get("metric_name", source.title)
    return (
        f"Metric anomaly on '{metric_name}' preceded error '{target.title}' by "
        f"{_format_duration(lag)}"
    )


def _error_to_alert_reason(
    source: TimelineEntry,
    target: TimelineEntry,
    lag: timedelta,
) -> str:
    return (
        f"Error '{source.title}' preceded alert '{target.title}' by "
        f"{_format_duration(lag)}"
    )
