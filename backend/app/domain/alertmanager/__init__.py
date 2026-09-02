"""Alertmanager webhook ingestion."""

from app.domain.alertmanager.parse import (
    AlertmanagerParseError,
    parse_alertmanager_alert,
    parse_alertmanager_webhook,
)
from app.domain.alertmanager.service import (
    AlertIncidentOutcome,
    AlertmanagerWebhookError,
    AlertmanagerWebhookResult,
    AlertmanagerWebhookService,
)
from app.domain.alertmanager.types import (
    AlertmanagerAlert,
    AlertmanagerWebhookPayload,
)

__all__ = [
    "AlertIncidentOutcome",
    "AlertmanagerAlert",
    "AlertmanagerParseError",
    "AlertmanagerWebhookError",
    "AlertmanagerWebhookPayload",
    "AlertmanagerWebhookResult",
    "AlertmanagerWebhookService",
    "parse_alertmanager_alert",
    "parse_alertmanager_webhook",
]
