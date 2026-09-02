"""Threshold helpers for temporal correlation."""

from __future__ import annotations

from datetime import timedelta

from app.core.config import Settings
from app.domain.correlation.types import (
    CorrelationThresholds,
    DeploymentCorrelationThresholds,
    ServiceCorrelationThresholds,
)


def correlation_thresholds_from_settings(
    settings: Settings,
) -> CorrelationThresholds:
    """Build :class:`CorrelationThresholds` from application settings."""

    return CorrelationThresholds(
        deployment_to_error_max_lag=timedelta(
            minutes=settings.correlation_deployment_to_error_max_lag_minutes,
        ),
        metric_anomaly_to_error_max_lag=timedelta(
            minutes=settings.correlation_metric_anomaly_to_error_max_lag_minutes,
        ),
        error_to_alert_max_lag=timedelta(
            minutes=settings.correlation_error_to_alert_max_lag_minutes,
        ),
        min_score=settings.correlation_min_score,
    )


def deployment_correlation_thresholds_from_settings(
    settings: Settings,
) -> DeploymentCorrelationThresholds:
    """Build :class:`DeploymentCorrelationThresholds` from application settings."""

    return DeploymentCorrelationThresholds(
        deployment_lookback=timedelta(
            hours=settings.deployment_correlation_lookback_hours,
        ),
        deployment_to_error_max_lag=timedelta(
            minutes=settings.correlation_deployment_to_error_max_lag_minutes,
        ),
        min_relationship_score=settings.deployment_correlation_min_relationship_score,
    )


def service_correlation_thresholds_from_settings(
    settings: Settings,
) -> ServiceCorrelationThresholds:
    """Build :class:`ServiceCorrelationThresholds` from application settings."""

    return ServiceCorrelationThresholds(
        metric_anomaly_to_error_max_lag=timedelta(
            minutes=settings.correlation_metric_anomaly_to_error_max_lag_minutes,
        ),
        trace_to_error_max_lag=timedelta(
            minutes=settings.service_correlation_trace_to_error_max_lag_minutes,
        ),
        upstream_propagation_max_lag=timedelta(
            minutes=settings.service_correlation_upstream_max_lag_minutes,
        ),
        min_score=settings.service_correlation_min_score,
        same_service_weight=settings.service_correlation_same_service_weight,
        temporal_weight=settings.service_correlation_temporal_weight,
        dependency_weight=settings.service_correlation_dependency_weight,
        trace_weight=settings.service_correlation_trace_weight,
    )
