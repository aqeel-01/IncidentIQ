"""Shared AI provider types and result models."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AIProviderName(enum.StrEnum):
    """Supported AI inference backends."""

    OLLAMA = "ollama"
    GROQ = "groq"


class GenerateRequest(BaseModel):
    """Prompt payload for unstructured text generation."""

    model_config = ConfigDict(frozen=True)

    prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)


class GenerateResponse(BaseModel):
    """Unstructured text generation result."""

    model_config = ConfigDict(frozen=True)

    content: str
    provider: AIProviderName
    model: str
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class StructuredGenerateRequest(BaseModel):
    """Prompt payload for schema-constrained generation."""

    model_config = ConfigDict(frozen=True)

    prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)


class StructuredGenerateResponse(BaseModel):
    """Validated structured generation result."""

    model_config = ConfigDict(frozen=True)

    data: dict[str, Any]
    raw_content: str
    provider: AIProviderName
    model: str
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class AIProviderHealthResult(BaseModel):
    """Outcome of an AI provider ``health_check``."""

    model_config = ConfigDict(frozen=True)

    provider: AIProviderName
    healthy: bool
    detail: str
    model: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIRoutingPlan(BaseModel):
    """Resolved provider routing derived from application settings."""

    model_config = ConfigDict(frozen=True)

    ai_mode: str
    rca_model: str
    primary: AIProviderName
    fallback: AIProviderName | None = None
