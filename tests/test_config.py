"""Tests for centralized configuration loading and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_defaults_are_safe_for_development(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure ambient env vars don't leak into the test.
    for var in ("APP_ENV", "AI_MODE", "RCA_MODEL", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.ai_mode == "local"
    assert settings.rca_model == "large"
    assert settings.ai_enable_fallback is False
    assert settings.groq_api_key == ""  # secret default is empty, never hardcoded
    assert settings.rca_temperature == 0.1
    assert settings.rca_max_tokens == 2048


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AI_MODE", "hybrid")
    monkeypatch.setenv("GROQ_API_KEY", "secret-value")
    monkeypatch.setenv("RCA_MAX_TOKENS", "4096")

    settings = Settings(_env_file=None)

    assert settings.app_env == "production"
    assert settings.is_production is True
    assert settings.ai_mode == "hybrid"
    assert settings.groq_api_key == "secret-value"
    assert settings.rca_max_tokens == 4096


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("AI_MODE", "quantum"),
        ("RCA_MODEL", "medium"),
        ("AI_FALLBACK_PROVIDER", "openai"),
        ("APP_ENV", "chaos"),
    ],
)
def test_invalid_enum_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_numeric_bounds_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RCA_TEMPERATURE", "5.0")  # above allowed max of 2.0
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("RCA_TEMPERATURE", "0.1")
    monkeypatch.setenv("RCA_MAX_TOKENS", "0")  # must be > 0
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_required_urls_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    get_settings.cache_clear()
