"""Parse Alertmanager webhook alerts into canonical events."""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.models.enums import Severity
from app.domain.alertmanager.types import AlertmanagerAlert, AlertmanagerWebhookPayload
from app.domain.events import AlertEvent, AlertStatus


class AlertmanagerParseError(ValueError):
    """Raised when an Alertmanager alert cannot be converted."""


_ALERTMANAGER_ZERO_TIME = datetime(1, 1, 1, tzinfo=UTC)

_SERVICE_LABEL_KEYS = ("service", "job", "app", "application")
_ENVIRONMENT_LABEL_KEYS = ("environment", "env")


def _parse_rfc3339(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    if parsed <= _ALERTMANAGER_ZERO_TIME:
        return None
    return parsed


def _merge_labels(
    alert: AlertmanagerAlert,
    payload: AlertmanagerWebhookPayload,
) -> dict[str, str]:
    merged: dict[str, str] = {}
    merged.update(payload.commonLabels)
    merged.update(alert.labels)
    return merged


def _alert_status(raw_status: str) -> AlertStatus:
    normalized = raw_status.strip().lower()
    if normalized == "resolved":
        return AlertStatus.RESOLVED
    if normalized == "firing":
        return AlertStatus.FIRING
    msg = f"unsupported alert status: {raw_status!r}"
    raise AlertmanagerParseError(msg)


def severity_from_labels(labels: dict[str, str]) -> Severity:
    raw = labels.get("severity", labels.get("priority", "medium")).strip().lower()
    mapping = {
        "critical": Severity.CRITICAL,
        "error": Severity.HIGH,
        "warning": Severity.HIGH,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
        "info": Severity.INFO,
        "none": Severity.INFO,
    }
    return mapping.get(raw, Severity.MEDIUM)


def service_name_from_labels(labels: dict[str, str]) -> str | None:
    for key in _SERVICE_LABEL_KEYS:
        value = labels.get(key)
        if value and value.strip():
            return value.strip()
    return None


def environment_from_labels(labels: dict[str, str]) -> str:
    for key in _ENVIRONMENT_LABEL_KEYS:
        value = labels.get(key)
        if value and value.strip():
            return value.strip()
    return "production"


def incident_title_from_alert(labels: dict[str, str]) -> str:
    alertname = labels.get("alertname", "").strip()
    if not alertname:
        msg = "alert labels must include alertname"
        raise AlertmanagerParseError(msg)
    return alertname


def parse_alertmanager_alert(
    alert: AlertmanagerAlert,
    *,
    payload: AlertmanagerWebhookPayload,
) -> AlertEvent:
    """Convert one Alertmanager alert into a canonical :class:`AlertEvent`."""

    labels = _merge_labels(alert, payload)
    annotations = {**payload.commonAnnotations, **alert.annotations}
    status = _alert_status(alert.status)
    starts_at = _parse_rfc3339(alert.startsAt)
    ends_at = _parse_rfc3339(alert.endsAt)

    if status is AlertStatus.FIRING:
        timestamp = starts_at or datetime.now(UTC)
    else:
        timestamp = ends_at or starts_at or datetime.now(UTC)

    alertname = labels.get("alertname", "").strip()
    if not alertname:
        msg = "alert labels must include alertname"
        raise AlertmanagerParseError(msg)

    return AlertEvent(
        timestamp=timestamp,
        source=f"alertmanager:{payload.receiver}",
        source_type="alertmanager",
        source_id=alert.fingerprint,
        service=service_name_from_labels(labels),
        environment=environment_from_labels(labels),
        name=alertname,
        status=status,
        severity=severity_from_labels(labels),
        labels=labels,
        annotations=annotations,
        raw_data=alert.model_dump(),
        normalized_data={
            "starts_at": starts_at.isoformat() if starts_at else None,
            "ends_at": ends_at.isoformat() if ends_at else None,
            "generator_url": alert.generatorURL,
        },
    )


def parse_alertmanager_webhook(payload: AlertmanagerWebhookPayload) -> list[AlertEvent]:
    """Parse every alert in a webhook payload."""

    return [
        parse_alertmanager_alert(alert, payload=payload) for alert in payload.alerts
    ]
