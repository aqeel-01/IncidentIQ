"""RCA configuration helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings


class RCAEngineConfig(BaseModel):
    """Runtime configuration for the RCA engine."""

    model_config = ConfigDict(frozen=True)

    engine_version: str = "1.0"
    prompt_version: str = "v1"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, gt=0)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    confident_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    min_evidence_quality: int = Field(default=30, ge=0, le=100)


def rca_prompt_version_from_settings(settings: Settings) -> str:
    """Return the configured RCA prompt version."""

    return settings.rca_prompt_version


def rca_engine_config_from_settings(settings: Settings) -> RCAEngineConfig:
    """Build :class:`RCAEngineConfig` from application settings."""

    return RCAEngineConfig(
        engine_version=settings.rca_engine_version,
        prompt_version=settings.rca_prompt_version,
        temperature=settings.rca_temperature,
        max_tokens=settings.rca_max_tokens,
        min_confidence=settings.rca_min_confidence,
        confident_threshold=settings.rca_confident_threshold,
        min_evidence_quality=settings.rca_min_evidence_quality,
    )
