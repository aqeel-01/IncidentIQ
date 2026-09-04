"""Deterministic IncidentIQ end-to-end demonstration."""

from app.domain.demo.report import format_demo_report
from app.domain.demo.runner import run_demo, write_demo_result
from app.domain.demo.scenario import (
    DEMO_INCIDENT_TITLE,
    DEMO_JOB_ID,
    DEMO_SERVICE,
    build_demo_sources,
    write_demo_log_file,
)
from app.domain.demo.types import DemoResult

__all__ = [
    "DEMO_INCIDENT_TITLE",
    "DEMO_JOB_ID",
    "DEMO_SERVICE",
    "DemoResult",
    "build_demo_sources",
    "format_demo_report",
    "run_demo",
    "write_demo_log_file",
    "write_demo_result",
]
