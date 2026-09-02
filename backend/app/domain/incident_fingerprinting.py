"""Deterministic incident fingerprinting for deduplication."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.domain.normalization.fields import normalize_environment
from app.domain.normalization.message import normalize_message_pattern

_JSON_SEPARATORS = (",", ":")


def _canonical_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def problem_identity_from_title(title: str) -> str:
    """Normalize an incident title into a stable alert/problem identity."""

    normalized = normalize_message_pattern(title)
    return normalized or title.strip()


def build_incident_fingerprint_material(
    *,
    service_id: int | None,
    environment: str,
    problem_identity: str,
) -> dict[str, str]:
    """Build ordered properties hashed into an incident fingerprint."""

    normalized_environment = (
        normalize_environment(environment) or environment.strip().lower()
    )
    return {
        "service_id": _canonical_value(service_id),
        "environment": normalized_environment,
        "problem_identity": _canonical_value(problem_identity),
    }


def compute_incident_fingerprint(
    *,
    service_id: int | None,
    environment: str,
    problem_identity: str,
) -> str:
    """Return a stable 64-character SHA-256 hex incident fingerprint."""

    material = build_incident_fingerprint_material(
        service_id=service_id,
        environment=environment,
        problem_identity=problem_identity,
    )
    payload = json.dumps(
        material, sort_keys=True, separators=_JSON_SEPARATORS, ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_incident_fingerprint_from_title(
    *,
    service_id: int | None,
    environment: str,
    title: str,
) -> str:
    """Fingerprint an incident from its title and scope attributes."""

    return compute_incident_fingerprint(
        service_id=service_id,
        environment=environment,
        problem_identity=problem_identity_from_title(title),
    )
