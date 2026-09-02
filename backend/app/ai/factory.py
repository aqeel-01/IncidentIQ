"""Resolve configured AI providers without vendor-specific imports."""

from __future__ import annotations

from app.ai.provider import AIProvider
from app.ai.registry import AIProviderRegistry
from app.ai.types import AIProviderName
from app.core.config import Settings


def register_default_providers(
    registry: AIProviderRegistry,
    settings: Settings,
) -> AIProviderRegistry:
    """Register built-in provider implementations on ``registry``."""

    from app.ai.providers.groq import create_groq_provider
    from app.ai.providers.ollama import create_ollama_provider

    registry.register(
        AIProviderName.OLLAMA,
        lambda: create_ollama_provider(settings),
        replace=True,
    )
    registry.register(
        AIProviderName.GROQ,
        lambda: create_groq_provider(settings),
        replace=True,
    )
    return registry


def default_ai_provider_registry(settings: Settings) -> AIProviderRegistry:
    """Create a registry with the default provider implementations."""

    return register_default_providers(AIProviderRegistry(), settings)


def resolve_provider(
    settings: Settings,
    registry: AIProviderRegistry,
    *,
    provider_name: AIProviderName | None = None,
) -> AIProvider:
    """Instantiate a routed provider for the given or configured name."""

    from app.ai.router import AIModelRouter

    router = AIModelRouter(settings, registry)
    if provider_name is not None:
        return router.get_provider_by_name(provider_name)
    return router.get_provider()
