"""Enumerations shared across ORM models.

Stored as strings (``native_enum=False`` at the column level) so the same
definitions work identically on PostgreSQL and on SQLite (used by tests) without
managing native database enum types.
"""

from __future__ import annotations

import enum


class IncidentStatus(enum.StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    IDENTIFIED = "IDENTIFIED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Severity(enum.StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventType(enum.StrEnum):
    """Canonical event categories (see SRS §4)."""

    LOG = "LOG"
    METRIC = "METRIC"
    ALERT = "ALERT"
    DEPLOYMENT = "DEPLOYMENT"
    TRACE = "TRACE"


class EvidenceSource(enum.StrEnum):
    ANOMALY_DETECTION = "anomaly_detection"
    TEMPORAL_CORRELATION = "temporal_correlation"
    DEPLOYMENT_CORRELATION = "deployment_correlation"
    SERVICE_CORRELATION = "service_correlation"
    TIMELINE_MARKER = "timeline_marker"


class EvidenceStance(enum.StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"


class EvidenceRelationKind(enum.StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CORRELATES_WITH = "correlates_with"
    CAUSED_BY = "caused_by"
    RELATED_TO = "related_to"


class ProjectRole(enum.StrEnum):
    """Project-scoped RBAC roles (least → most privileged)."""

    VIEWER = "VIEWER"
    ENGINEER = "ENGINEER"
    ADMIN = "ADMIN"
