"""Groq provider configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.ai.errors import AIProviderConfigurationError
from app.core.config import Settings

_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProviderConfig(BaseModel):
    """Runtime configuration for the Groq AI provider."""

    model_config = ConfigDict(frozen=True)

    api_key: SecretStr
    model: str = Field(min_length=1)
    base_url: str = Field(default=_DEFAULT_BASE_URL, min_length=1)
    default_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    default_max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=60.0, gt=0)

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.get_secret_value().strip())


def groq_provider_config_from_settings(settings: Settings) -> GroqProviderConfig:
    """Build Groq provider settings from application configuration."""

    if not settings.groq_api_key.strip():
        msg = "groq api key is not configured; set GROQ_API_KEY"
        raise AIProviderConfigurationError(msg)
    if not settings.groq_model.strip():
        msg = "groq model is not configured; set GROQ_MODEL"
        raise AIProviderConfigurationError(msg)

    return GroqProviderConfig(
        api_key=SecretStr(settings.groq_api_key),
        model=settings.groq_model,
        default_temperature=settings.rca_temperature,
        default_max_tokens=settings.rca_max_tokens,
        timeout_seconds=settings.groq_timeout_seconds,
    )
