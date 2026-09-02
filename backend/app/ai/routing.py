"""AI provider routing derived from application settings."""

from __future__ import annotations

from app.ai.types import AIProviderName, AIRoutingPlan
from app.core.config import AIMode, FallbackProvider, RCAModelSize, Settings


def select_primary_provider_name(settings: Settings) -> AIProviderName:
    """Choose the primary provider from ``AI_MODE``."""

    mode_to_provider: dict[AIMode, AIProviderName] = {
        "local": AIProviderName.OLLAMA,
        "cloud": AIProviderName.GROQ,
        "hybrid": AIProviderName.OLLAMA,
    }
    return mode_to_provider[settings.ai_mode]


def select_fallback_provider_name(settings: Settings) -> AIProviderName:
    """Choose the configured fallback provider."""

    fallback_to_provider: dict[FallbackProvider, AIProviderName] = {
        "ollama": AIProviderName.OLLAMA,
        "groq": AIProviderName.GROQ,
    }
    return fallback_to_provider[settings.ai_fallback_provider]


def is_fallback_enabled(settings: Settings) -> bool:
    """Return whether provider fallback should be active."""

    return settings.ai_mode == "hybrid" or settings.ai_enable_fallback


def routing_plan_from_settings(settings: Settings) -> AIRoutingPlan:
    """Build a routing plan from environment-backed settings."""

    primary = select_primary_provider_name(settings)
    fallback: AIProviderName | None = None
    if is_fallback_enabled(settings):
        candidate = select_fallback_provider_name(settings)
        if candidate != primary:
            fallback = candidate

    return AIRoutingPlan(
        ai_mode=settings.ai_mode,
        rca_model=settings.rca_model,
        primary=primary,
        fallback=fallback,
    )


def resolve_rca_model_size(settings: Settings) -> RCAModelSize:
    """Return the configured RCA model size for Ollama routing."""

    return settings.rca_model
