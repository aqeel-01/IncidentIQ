"""Investigation source collection types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.domain.events import CanonicalEventBase


@dataclass(frozen=True, slots=True)
class InvestigationSources:
    """Raw and canonical inputs for an investigation pipeline run."""

    canonical_events: tuple[CanonicalEventBase, ...] = ()
    raw_log_lines: tuple[str, ...] = ()
    log_file_paths: tuple[Path, ...] = ()


@dataclass(slots=True)
class CollectedInvestigationSources:
    """Sources gathered during the collect stage."""

    canonical_events: list[CanonicalEventBase] = field(default_factory=list)
    raw_log_lines: list[str] = field(default_factory=list)
    log_file_paths: list[Path] = field(default_factory=list)
