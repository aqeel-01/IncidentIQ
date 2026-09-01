"""Centralized application configuration.

All runtime configuration is loaded from environment variables (optionally via a
local ``.env`` file) using Pydantic Settings. This keeps configuration in one
place, provides validation with clear errors, and ensures secrets never live in
source code.

Business logic and providers must read configuration from :func:`get_settings`
rather than accessing ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AIMode = Literal["local", "cloud", "hybrid"]
RCAModelSize = Literal["small", "large"]
FallbackProvider = Literal["ollama", "groq"]


class Settings(BaseSettings):
    """Application settings loaded from the environment.

    Field names map to environment variables case-insensitively, e.g. the
    ``database_url`` field is populated from ``DATABASE_URL``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "IncidentIQ"
    app_version: str = "0.1.0"

    # --- Infrastructure ------------------------------------------------------
    # Safe local-development defaults; override per environment.
    database_url: str = "postgresql://incidentiq:incidentiq@localhost:5432/incidentiq"
    redis_url: str = "redis://localhost:6379/0"

    # Optional services: unset by default so the app remains usable without them.
    opensearch_url: str | None = None
    prometheus_url: str | None = None

    # --- AI providers --------------------------------------------------------
    ai_mode: AIMode = "local"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model_small: str = ""
    ollama_model_large: str = ""

    rca_model: RCAModelSize = "large"

    # Secret: must be provided via environment, never committed.
    groq_api_key: str = ""
    groq_model: str = ""

    ai_enable_fallback: bool = False
    ai_fallback_provider: FallbackProvider = "groq"

    rca_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    rca_max_tokens: int = Field(default=2048, gt=0)

    @field_validator("database_url", "redis_url")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Caching avoids re-parsing the environment on every request. Tests that need
    fresh settings can call ``get_settings.cache_clear()``.
    """

    return Settings()
