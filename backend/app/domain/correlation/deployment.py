"""Deployment correlation evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.domain.correlation.types import (
    CorrelationKind,
    DeploymentCorrelationAssessment,
    DeploymentCorrelationThresholds,
    DeploymentEvidence,
    DeploymentEvidenceKind,
    TemporalCorrelation,
)
from app.domain.timeline.types import TimelineEntry, TimelineMarkers

_STRONG_SUPPORTING_KINDS = frozenset(
    {
        DeploymentEvidenceKind.DEPLOYMENT_BEFORE_FIRST_ERROR,
        DeploymentEvidenceKind.DEPLOYMENT_BEFORE_FIRST_ANOMALY,
        DeploymentEvidenceKind.DEPLOYMENT_ERROR_TEMPORAL_LINK,
        DeploymentEvidenceKind.CHANGED_COMPONENT_OVERLAP,
    }
)

_FATAL_CONTRADICTING_KINDS = frozenset(
    {
        DeploymentEvidenceKind.FIRST_ERROR_BEFORE_DEPLOYMENT,
        DeploymentEvidenceKind.FIRST_ANOMALY_BEFORE_DEPLOYMENT,
    }
)


def evaluate_deployment_correlation(
    *,
    incident_started_at: datetime,
    affected_service: str | None,
    markers: TimelineMarkers,
    correlations: Sequence[TemporalCorrelation],
    thresholds: DeploymentCorrelationThresholds | None = None,
) -> DeploymentCorrelationAssessment:
    """Assess temporal and logical links between an incident and a deployment."""

    config = thresholds or DeploymentCorrelationThresholds()
    incident_start = _to_utc(incident_started_at)
    deployment = markers.recent_deployment
    supporting: list[DeploymentEvidence] = []
    contradicting: list[DeploymentEvidence] = []

    if deployment is None:
        contradicting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.NO_RECENT_DEPLOYMENT,
                detail=(
                    "No deployment was found within "
                    f"{_format_duration(config.deployment_lookback)} "
                    "before incident start"
                ),
                weight=0.5,
            )
        )
        return _build_assessment(
            deployment=None,
            supporting=supporting,
            contradicting=contradicting,
            thresholds=config,
        )

    deployment_time = _to_utc(deployment.timestamp)
    lookback_start = incident_start - config.deployment_lookback
    if deployment_time < lookback_start:
        contradicting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.NO_RECENT_DEPLOYMENT,
                detail=(
                    f"Deployment '{deployment.title}' is outside the "
                    f"{_format_duration(config.deployment_lookback)} lookback window"
                ),
                weight=0.5,
            )
        )
        return _build_assessment(
            deployment=deployment,
            supporting=supporting,
            contradicting=contradicting,
            thresholds=config,
        )

    supporting.append(
        DeploymentEvidence(
            kind=DeploymentEvidenceKind.RECENT_DEPLOYMENT,
            detail=(
                f"Deployment '{deployment.title}' occurred "
                f"{_format_duration(incident_start - deployment_time)} "
                "before incident start"
            ),
            weight=0.15,
        )
    )

    if deployment_time > incident_start:
        contradicting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.DEPLOYMENT_AFTER_INCIDENT_START,
                detail=(
                    f"Deployment '{deployment.title}' occurred after incident start"
                ),
                weight=0.35,
            )
        )

    _evaluate_first_error(
        deployment=deployment,
        first_error=markers.first_relevant_error,
        max_lag=config.deployment_to_error_max_lag,
        supporting=supporting,
        contradicting=contradicting,
    )
    _evaluate_first_anomaly(
        deployment=deployment,
        first_anomaly=markers.first_anomaly,
        max_lag=config.deployment_to_error_max_lag,
        supporting=supporting,
        contradicting=contradicting,
    )
    _evaluate_temporal_link(
        deployment=deployment,
        correlations=correlations,
        supporting=supporting,
    )
    _evaluate_service_match(
        deployment=deployment,
        affected_service=affected_service,
        supporting=supporting,
        contradicting=contradicting,
    )
    _evaluate_changed_components(
        deployment=deployment,
        first_error=markers.first_relevant_error,
        supporting=supporting,
    )
    _evaluate_missing_error_link(
        deployment=deployment,
        first_error=markers.first_relevant_error,
        correlations=correlations,
        contradicting=contradicting,
    )

    return _build_assessment(
        deployment=deployment,
        supporting=supporting,
        contradicting=contradicting,
        thresholds=config,
    )


def _evaluate_first_error(
    *,
    deployment: TimelineEntry,
    first_error: TimelineEntry | None,
    max_lag: timedelta,
    supporting: list[DeploymentEvidence],
    contradicting: list[DeploymentEvidence],
) -> None:
    if first_error is None:
        return

    lag = first_error.timestamp - deployment.timestamp
    if lag.total_seconds() <= 0:
        contradicting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.FIRST_ERROR_BEFORE_DEPLOYMENT,
                detail=(
                    f"First error '{first_error.title}' occurred before deployment "
                    f"'{deployment.title}'"
                ),
                weight=0.5,
            )
        )
        return

    if lag <= max_lag:
        supporting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.DEPLOYMENT_BEFORE_FIRST_ERROR,
                detail=(
                    f"Deployment '{deployment.title}' preceded first error "
                    f"'{first_error.title}' by {_format_duration(lag)}"
                ),
                weight=0.35,
            )
        )


def _evaluate_first_anomaly(
    *,
    deployment: TimelineEntry,
    first_anomaly: TimelineEntry | None,
    max_lag: timedelta,
    supporting: list[DeploymentEvidence],
    contradicting: list[DeploymentEvidence],
) -> None:
    if first_anomaly is None:
        return

    lag = first_anomaly.timestamp - deployment.timestamp
    if lag.total_seconds() <= 0:
        contradicting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.FIRST_ANOMALY_BEFORE_DEPLOYMENT,
                detail=(
                    f"First anomaly '{first_anomaly.title}' occurred before deployment "
                    f"'{deployment.title}'"
                ),
                weight=0.4,
            )
        )
        return

    if lag <= max_lag:
        supporting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.DEPLOYMENT_BEFORE_FIRST_ANOMALY,
                detail=(
                    f"Deployment '{deployment.title}' preceded first anomaly "
                    f"'{first_anomaly.title}' by {_format_duration(lag)}"
                ),
                weight=0.25,
            )
        )


def _evaluate_temporal_link(
    *,
    deployment: TimelineEntry,
    correlations: Sequence[TemporalCorrelation],
    supporting: list[DeploymentEvidence],
) -> None:
    for correlation in correlations:
        if correlation.kind is not CorrelationKind.DEPLOYMENT_TO_ERROR:
            continue
        if correlation.source.id != deployment.id:
            continue
        supporting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.DEPLOYMENT_ERROR_TEMPORAL_LINK,
                detail=(
                    f"{correlation.reason} (correlation score "
                    f"{correlation.correlation_score:.2f})"
                ),
                weight=round(0.2 + (0.2 * correlation.correlation_score), 4),
            )
        )
        return


def _evaluate_service_match(
    *,
    deployment: TimelineEntry,
    affected_service: str | None,
    supporting: list[DeploymentEvidence],
    contradicting: list[DeploymentEvidence],
) -> None:
    if not affected_service:
        return

    normalized = deployment.metadata.get("normalized_data", {})
    repository = str(normalized.get("repository", ""))

    if repository and (
        affected_service.lower() in repository.lower()
        or affected_service.lower() in deployment.title.lower()
    ):
        supporting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.AFFECTED_SERVICE_MATCH,
                detail=(
                    f"Deployment appears associated with affected service "
                    f"'{affected_service}'"
                ),
                weight=0.2,
            )
        )
        return

    if repository and affected_service.lower() not in repository.lower():
        contradicting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.AFFECTED_SERVICE_MISMATCH,
                detail=(
                    f"Deployment repository '{repository}' does not match affected "
                    f"service '{affected_service}'"
                ),
                weight=0.2,
            )
        )


def _evaluate_changed_components(
    *,
    deployment: TimelineEntry,
    first_error: TimelineEntry | None,
    supporting: list[DeploymentEvidence],
) -> None:
    if first_error is None:
        return

    normalized = deployment.metadata.get("normalized_data", {})
    changed_files = normalized.get("changed_files") or []
    if not changed_files:
        return

    error_text = " ".join(
        part for part in (first_error.title, first_error.summary) if part
    )
    overlaps = _changed_file_overlap(changed_files, error_text)
    if not overlaps:
        return

    supporting.append(
        DeploymentEvidence(
            kind=DeploymentEvidenceKind.CHANGED_COMPONENT_OVERLAP,
            detail=(
                "Changed components overlap with first error context: "
                + ", ".join(overlaps[:5])
            ),
            weight=0.25,
        )
    )


def _evaluate_missing_error_link(
    *,
    deployment: TimelineEntry,
    first_error: TimelineEntry | None,
    correlations: Sequence[TemporalCorrelation],
    contradicting: list[DeploymentEvidence],
) -> None:
    if first_error is None:
        return

    has_link = any(
        correlation.kind is CorrelationKind.DEPLOYMENT_TO_ERROR
        and correlation.source.id == deployment.id
        for correlation in correlations
    )
    if has_link:
        return

    contradicting.append(
        DeploymentEvidence(
            kind=DeploymentEvidenceKind.MISSING_DEPLOYMENT_ERROR_LINK,
            detail=(
                "Errors are present but no qualifying deployment-to-error temporal "
                "link was found within the configured lag window"
            ),
            weight=0.2,
        )
    )


def _build_assessment(
    *,
    deployment: TimelineEntry | None,
    supporting: list[DeploymentEvidence],
    contradicting: list[DeploymentEvidence],
    thresholds: DeploymentCorrelationThresholds,
) -> DeploymentCorrelationAssessment:
    has_strong_support = any(
        item.kind in _STRONG_SUPPORTING_KINDS for item in supporting
    )
    has_fatal_contradiction = any(
        item.kind in _FATAL_CONTRADICTING_KINDS for item in contradicting
    )

    if deployment is not None and not has_strong_support:
        contradicting.append(
            DeploymentEvidence(
                kind=DeploymentEvidenceKind.DEPLOYMENT_ALONE_INSUFFICIENT,
                detail=(
                    "A recent deployment alone does not establish incident "
                    "relationship; additional temporal or logical signals are required"
                ),
                weight=0.3,
            )
        )

    supporting_total = sum(item.weight for item in supporting)
    contradicting_total = sum(item.weight for item in contradicting)
    relationship_score = round(
        max(0.0, min(1.0, 0.5 + ((supporting_total - contradicting_total) * 0.25))),
        4,
    )

    is_related = (
        deployment is not None
        and has_strong_support
        and not has_fatal_contradiction
        and relationship_score >= thresholds.min_relationship_score
    )

    return DeploymentCorrelationAssessment(
        is_related=is_related,
        relationship_score=relationship_score,
        deployment=deployment,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        summary=_build_summary(
            deployment=deployment,
            is_related=is_related,
            supporting=supporting,
            contradicting=contradicting,
        ),
    )


def _build_summary(
    *,
    deployment: TimelineEntry | None,
    is_related: bool,
    supporting: list[DeploymentEvidence],
    contradicting: list[DeploymentEvidence],
) -> str:
    if deployment is None:
        return (
            "No qualifying recent deployment was found for this incident. "
            "Deployment correlation cannot be assessed."
        )

    if is_related:
        signals = ", ".join(
            item.kind.value.replace("_", " ") for item in supporting[:3]
        )
        return (
            f"The incident may be temporally and logically associated with "
            f"deployment '{deployment.title}' ({signals}). "
            "This assessment is based on timing and context only and does not "
            "establish causation."
        )

    if any(
        item.kind in _FATAL_CONTRADICTING_KINDS for item in contradicting
    ):
        return (
            f"Signals appeared before deployment '{deployment.title}', so a deployment "
            "relationship is unlikely. This does not rule out other root causes."
        )

    return (
        f"A recent deployment '{deployment.title}' was found, but supporting signals "
        "are insufficient to suggest a meaningful relationship. "
        "Deployment timing alone does not imply causation."
    )


def _changed_file_overlap(changed_files: Sequence[str], error_text: str) -> list[str]:
    error_lower = error_text.lower()
    matches: list[str] = []
    for path in changed_files:
        normalized_path = str(path).strip()
        if not normalized_path:
            continue
        basename = normalized_path.rsplit("/", 1)[-1]
        if basename.lower() in error_lower or normalized_path.lower() in error_lower:
            matches.append(normalized_path)
    return matches


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
