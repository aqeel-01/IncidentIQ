"""ORM models.

Importing this package registers every model on ``Base.metadata``. Alembic's
``env.py`` imports it so autogenerate sees the full schema.
"""

from __future__ import annotations

from app.db.models.enums import EventType, IncidentStatus, Severity
from app.db.models.error_group import ErrorGroup
from app.db.models.event import Event
from app.db.models.incident import Incident
from app.db.models.log_upload import LogUpload, LogUploadStatus
from app.db.models.organization import Organization
from app.db.models.project import Project
from app.db.models.service import Service
from app.db.models.user import User

__all__ = [
    "EventType",
    "IncidentStatus",
    "Severity",
    "Organization",
    "User",
    "Project",
    "Service",
    "Incident",
    "Event",
    "ErrorGroup",
    "LogUpload",
    "LogUploadStatus",
]
