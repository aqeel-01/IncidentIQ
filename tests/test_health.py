"""Tests for the health and readiness endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.api.routes.health as health_route
from app.core.config import Settings
from app.core.health import CheckResult


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "IncidentIQ"
    assert body["environment"] == "test"


def test_readiness_ok_when_dependencies_healthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_checks(_settings: Settings, _engine=None) -> list[CheckResult]:
        return [
            CheckResult("postgres", True, True, "ok"),
            CheckResult("redis", True, True, "ok"),
        ]

    monkeypatch.setattr(health_route, "run_readiness_checks", fake_checks)

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["postgres"]["healthy"] is True
    assert body["checks"]["redis"]["healthy"] is True


def test_readiness_503_when_required_dependency_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_checks(_settings: Settings, _engine=None) -> list[CheckResult]:
        return [
            CheckResult("postgres", False, True, "unavailable: refused"),
            CheckResult("redis", True, True, "ok"),
        ]

    monkeypatch.setattr(health_route, "run_readiness_checks", fake_checks)

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"]["healthy"] is False


def test_readiness_ok_when_only_optional_dependency_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An optional (non-required) dependency being down must not fail readiness.
    async def fake_checks(_settings: Settings, _engine=None) -> list[CheckResult]:
        return [
            CheckResult("postgres", True, True, "ok"),
            CheckResult("redis", True, True, "ok"),
            CheckResult("opensearch", False, False, "unavailable"),
        ]

    monkeypatch.setattr(health_route, "run_readiness_checks", fake_checks)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
