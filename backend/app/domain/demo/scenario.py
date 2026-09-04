"""Deterministic IncidentIQ demo scenario: payments-api deployment regression."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.models.enums import Severity
from app.domain.events import (
    AlertEvent,
    AlertStatus,
    DeploymentEvent,
    LogEvent,
    MetricEvent,
)
from app.domain.investigation.sources import InvestigationSources

DEMO_JOB_ID = "demo-payments-deploy-regression"
DEMO_SERVICE = "payments-api"
DEMO_INCIDENT_TITLE = "Checkout failures after payments-api v1.2.2"
DEMO_BASE_TIME = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def demo_timestamp(minutes: int = 0, seconds: int = 0) -> datetime:
    return DEMO_BASE_TIME + timedelta(minutes=minutes, seconds=seconds)


def _envelope() -> dict:
    return {
        "source": "incidentiq-demo",
        "source_type": "demo",
        "environment": "production",
        "raw_data": {"scenario": "payments-deploy-regression", "seed": True},
    }


def build_demo_sources(*, log_file_path: Path | None = None) -> InvestigationSources:
    """Build logs + metrics + alert + deployment signals for the demo incident."""

    events = (
        DeploymentEvent(
            timestamp=demo_timestamp(-60),
            version="v1.2.2",
            commit_sha="deploy123",
            repository="payments-api",
            service=DEMO_SERVICE,
            source="azure_devops:pipelines",
            source_type="azure_devops",
            environment="production",
            raw_data={
                "scenario": "payments-deploy-regression",
                "pipeline": "payments-api-release",
            },
        ),
        MetricEvent(
            timestamp=demo_timestamp(-15),
            metric_name="error_rate",
            value=0.12,
            service=DEMO_SERVICE,
            **_envelope(),
        ),
        MetricEvent(
            timestamp=demo_timestamp(-10),
            metric_name="error_rate",
            value=0.9,
            service=DEMO_SERVICE,
            **_envelope(),
        ),
        MetricEvent(
            timestamp=demo_timestamp(-8),
            metric_name="db_connection_errors",
            value=47,
            service=DEMO_SERVICE,
            **_envelope(),
        ),
        LogEvent(
            timestamp=demo_timestamp(0),
            message="connection timeout talking to database",
            severity=Severity.HIGH,
            service=DEMO_SERVICE,
            host="payments-api-7f9c",
            request_id="req-1001",
            **_envelope(),
        ),
        LogEvent(
            timestamp=demo_timestamp(0, seconds=20),
            message="connection timeout talking to database",
            severity=Severity.HIGH,
            service=DEMO_SERVICE,
            host="payments-api-7f9c",
            request_id="req-1002",
            **_envelope(),
        ),
        LogEvent(
            timestamp=demo_timestamp(1),
            message="checkout capture failed due to database timeout",
            severity=Severity.HIGH,
            service=DEMO_SERVICE,
            host="payments-api-7f9c",
            request_id="req-1003",
            **_envelope(),
        ),
        AlertEvent(
            timestamp=demo_timestamp(5),
            name="HighErrorRate",
            status=AlertStatus.FIRING,
            severity=Severity.HIGH,
            service=DEMO_SERVICE,
            labels={"service": DEMO_SERVICE, "env": "production"},
            **_envelope(),
        ),
    )

    raw_lines = (
        (
            "2026-09-01T12:00:00Z ERROR payments-api "
            "connection timeout talking to database"
        ),
        (
            "2026-09-01T12:00:20Z ERROR payments-api "
            "connection timeout talking to database"
        ),
        (
            "2026-09-01T12:01:00Z ERROR payments-api "
            "checkout capture failed due to database timeout"
        ),
    )

    paths: tuple[Path, ...] = ()
    if log_file_path is not None:
        paths = (log_file_path,)

    return InvestigationSources(
        canonical_events=events,
        raw_log_lines=raw_lines,
        log_file_paths=paths,
    )


def write_demo_log_file(path: Path) -> Path:
    """Write a deterministic JSONL log corpus for streaming parse coverage."""

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "timestamp": demo_timestamp(0).isoformat(),
            "level": "ERROR",
            "service": DEMO_SERVICE,
            "host": "payments-api-7f9c",
            "message": "connection timeout talking to database",
            "request_id": "req-2001",
            "environment": "production",
        },
        {
            "timestamp": demo_timestamp(0, seconds=45).isoformat(),
            "level": "ERROR",
            "service": DEMO_SERVICE,
            "host": "payments-api-7f9c",
            "message": "connection timeout talking to database",
            "request_id": "req-2002",
            "environment": "production",
        },
        {
            "timestamp": demo_timestamp(2).isoformat(),
            "level": "ERROR",
            "service": DEMO_SERVICE,
            "host": "payments-api-7f9c",
            "message": "checkout capture failed due to database timeout",
            "request_id": "req-2003",
            "environment": "production",
        },
    ]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")))
            handle.write("\n")
    return path
