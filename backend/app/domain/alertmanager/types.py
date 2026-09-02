"""Alertmanager webhook payload schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertmanagerAlert(BaseModel):
    """A single alert entry from an Alertmanager webhook."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(min_length=1)
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    endsAt: str | None = None
    generatorURL: str | None = None
    fingerprint: str | None = None


class AlertmanagerWebhookPayload(BaseModel):
    """Validated Alertmanager webhook body (v4-compatible)."""

    model_config = ConfigDict(extra="allow")

    receiver: str = Field(min_length=1)
    status: str = Field(min_length=1)
    alerts: list[AlertmanagerAlert] = Field(min_length=1)
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str | None = None
    version: str | None = None
    groupKey: str | None = None
    truncatedAlerts: int | None = None

    def model_dump_alerts(self) -> list[dict[str, Any]]:
        return [alert.model_dump() for alert in self.alerts]
