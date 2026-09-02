"""Ollama provider configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.errors import AIProviderConfigurationError
from app.core.config import RCAModelSize, Settings


class OllamaProviderConfig(BaseModel):
    """Runtime configuration for the Ollama AI provider."""

    model_config = ConfigDict(frozen=True)

    base_url: str = Field(min_length=1)
    model_small: str = ""
    model_large: str = ""
    model_size: RCAModelSize = "large"
    default_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    default_max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=60.0, gt=0)

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def active_model(self) -> str:
        model = self.model_small if self.model_size == "small" else self.model_large
        if not model:
            size_label = "small" if self.model_size == "small" else "large"
            msg = (
                f"ollama {size_label} model is not configured; "
                f"set OLLAMA_MODEL_{size_label.upper()}"
            )
            raise AIProviderConfigurationError(msg)
        return model


def ollama_provider_config_from_settings(
    settings: Settings,
    *,
    model_size: RCAModelSize | None = None,
) -> OllamaProviderConfig:
    """Build Ollama provider settings from application configuration."""

    return OllamaProviderConfig(
        base_url=settings.ollama_base_url,
        model_small=settings.ollama_model_small,
        model_large=settings.ollama_model_large,
        model_size=model_size or settings.rca_model,
        default_temperature=settings.rca_temperature,
        default_max_tokens=settings.rca_max_tokens,
        timeout_seconds=settings.ollama_timeout_seconds,
    )


def resolve_ollama_model_name(
    config: OllamaProviderConfig,
    model_size: Literal["small", "large"],
) -> str:
    """Resolve a configured Ollama model name by size."""

    return config.model_copy(update={"model_size": model_size}).active_model
