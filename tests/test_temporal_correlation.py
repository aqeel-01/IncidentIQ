"""Tests for temporal correlation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.models.enums import Severity
from app.domain.correlation import (
    CorrelationKind,
    CorrelationThresholds,
    TemporalCorrelation,
    correlate_temporal,
    correlation_score,
    correlation_thresholds_from_settings,
)
from app.domain.timeline.types import TimelineCategory, TimelineEntry


def _ts(minutes: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _entry(
    entry_id: str,
    category: TimelineCategory,
    *,
    minutes: int = 0,
    title: str = "event",
    severity: Severity | None = None,
    metadata: dict | None = None,
) -> TimelineEntry:
    return TimelineEntry(
        id=entry_id,
        category=category,
        timestamp=_ts(minutes),
        title=title,
        severity=severity,
        metadata=metadata or {},
    )


def test_correlation_score_decays_linearly_with_lag() -> None:
    max_lag = timedelta(minutes=10)

    assert correlation_score(timedelta(minutes=0), max_lag=max_lag) == 1.0
    assert correlation_score(timedelta(minutes=5), max_lag=max_lag) == 0.5
    assert correlation_score(timedelta(minutes=10), max_lag=max_lag) == 0.0
    assert correlation_score(timedelta(minutes=11), max_lag=max_lag) == 0.0


def test_correlation_thresholds_validate_positive_lags() -> None:
    with pytest.raises(ValidationError):
        CorrelationThresholds(
            deployment_to_error_max_lag=timedelta(seconds=0),
        )


def test_correlation_thresholds_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        correlation_deployment_to_error_max_lag_minutes=90,
        correlation_min_score=0.25,
    )
    thresholds = correlation_thresholds_from_settings(settings)

    assert thresholds.deployment_to_error_max_lag == timedelta(minutes=90)
    assert thresholds.min_score == 0.25


def test_deployment_to_error_correlation() -> None:
    entries = [
        _entry("event:1", TimelineCategory.DEPLOYMENT, minutes=0, title="v1.2.3"),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=10,
            title="database timeout",
        ),
    ]

    correlations = correlate_temporal(entries)

    assert len(correlations) == 1
    correlation = correlations[0]
    assert correlation.kind is CorrelationKind.DEPLOYMENT_TO_ERROR
    assert correlation.source.id == "event:1"
    assert correlation.target.id == "error_group:1"
    assert correlation.time_difference == timedelta(minutes=10)
    assert correlation.correlation_score == pytest.approx(0.916667, rel=1e-4)
    assert "Deployment 'v1.2.3'" in correlation.reason
    assert "database timeout" in correlation.reason


def test_metric_anomaly_to_error_correlation() -> None:
    entries = [
        _entry(
            "event:1",
            TimelineCategory.METRIC,
            minutes=0,
            title="error_rate",
            metadata={
                "anomaly": True,
                "normalized_data": {"metric_name": "error_rate", "value": 0.9},
            },
        ),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=5,
            title="checkout failed",
        ),
    ]

    correlations = correlate_temporal(
        entries,
        CorrelationThresholds(
            metric_anomaly_to_error_max_lag=timedelta(minutes=10),
        ),
    )

    assert len(correlations) == 1
    correlation = correlations[0]
    assert correlation.kind is CorrelationKind.METRIC_ANOMALY_TO_ERROR
    assert correlation.source.id == "event:1"
    assert correlation.target.id == "error_group:1"
    assert correlation.time_difference == timedelta(minutes=5)
    assert correlation.correlation_score == 0.5


def test_error_to_alert_correlation() -> None:
    entries = [
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=0,
            title="connection reset",
        ),
        _entry(
            "event:1",
            TimelineCategory.ALERT,
            minutes=3,
            title="HighErrorRate",
            metadata={"normalized_data": {"status": "FIRING"}},
        ),
    ]

    correlations = correlate_temporal(
        entries,
        CorrelationThresholds(error_to_alert_max_lag=timedelta(minutes=5)),
    )

    assert len(correlations) == 1
    correlation = correlations[0]
    assert correlation.kind is CorrelationKind.ERROR_TO_ALERT
    assert correlation.source.id == "error_group:1"
    assert correlation.target.id == "event:1"
    assert correlation.time_difference == timedelta(minutes=3)
    assert correlation.correlation_score == pytest.approx(0.4)


def test_high_severity_log_counts_as_error_for_correlation() -> None:
    entries = [
        _entry("event:1", TimelineCategory.DEPLOYMENT, minutes=0, title="v2.0.0"),
        _entry(
            "event:2",
            TimelineCategory.LOG,
            minutes=2,
            title="upstream timeout",
            severity=Severity.HIGH,
        ),
        _entry(
            "event:3",
            TimelineCategory.ALERT,
            minutes=4,
            title="LatencyAlert",
            metadata={"normalized_data": {"status": "FIRING"}},
        ),
    ]

    correlations = correlate_temporal(entries)

    kinds = {item.kind for item in correlations}
    assert CorrelationKind.DEPLOYMENT_TO_ERROR in kinds
    assert CorrelationKind.ERROR_TO_ALERT in kinds


def test_resolved_alerts_are_not_correlation_targets() -> None:
    entries = [
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=0,
            title="failure",
        ),
        _entry(
            "event:1",
            TimelineCategory.ALERT,
            minutes=2,
            title="ResolvedAlert",
            metadata={"normalized_data": {"status": "RESOLVED"}},
        ),
    ]

    correlations = correlate_temporal(entries)
    assert correlations == []


def test_events_outside_max_lag_are_not_correlated() -> None:
    entries = [
        _entry("event:1", TimelineCategory.DEPLOYMENT, minutes=0, title="v1.0.0"),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=180,
            title="late failure",
        ),
    ]

    correlations = correlate_temporal(
        entries,
        CorrelationThresholds(
            deployment_to_error_max_lag=timedelta(minutes=60),
        ),
    )
    assert correlations == []


def test_correlations_below_min_score_are_filtered() -> None:
    entries = [
        _entry("event:1", TimelineCategory.DEPLOYMENT, minutes=0, title="v1.0.0"),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=110,
            title="slow failure",
        ),
    ]

    correlations = correlate_temporal(
        entries,
        CorrelationThresholds(
            deployment_to_error_max_lag=timedelta(minutes=120),
            min_score=0.2,
        ),
    )
    assert correlations == []


def test_full_incident_chain_produces_three_correlations() -> None:
    entries = [
        _entry("event:1", TimelineCategory.DEPLOYMENT, minutes=0, title="v1.2.2"),
        _entry(
            "event:2",
            TimelineCategory.METRIC,
            minutes=8,
            title="error_rate",
            metadata={
                "anomaly": True,
                "normalized_data": {"metric_name": "error_rate", "value": 0.8},
            },
        ),
        _entry(
            "error_group:1",
            TimelineCategory.ERROR,
            minutes=10,
            title="connection timeout",
        ),
        _entry(
            "event:3",
            TimelineCategory.ALERT,
            minutes=15,
            title="HighErrorRate",
            metadata={"normalized_data": {"status": "FIRING"}},
        ),
    ]

    correlations = correlate_temporal(entries)
    kinds = [item.kind for item in correlations]

    assert kinds == [
        CorrelationKind.DEPLOYMENT_TO_ERROR,
        CorrelationKind.METRIC_ANOMALY_TO_ERROR,
        CorrelationKind.ERROR_TO_ALERT,
    ]
    assert all(isinstance(item, TemporalCorrelation) for item in correlations)
