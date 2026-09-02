"""AI model router for provider selection and fallback."""

from __future__ import annotations

from app.ai.errors import AIProviderRegistrationError
from app.ai.factory import register_default_providers
from app.ai.fallback import FallbackAIProvider
from app.ai.provider import AIProvider
from app.ai.registry import AIProviderRegistry
from app.ai.routing import routing_plan_from_settings
from app.ai.types import AIProviderName, AIRoutingPlan
from app.core.config import Settings


class AIModelRouter:
    """Route AI requests to configured providers based on settings."""

    def __init__(
        self,
        settings: Settings,
        registry: AIProviderRegistry | None = None,
    ) -> None:
        self._settings = settings
        if registry is None:
            registry = AIProviderRegistry()
            register_default_providers(registry, settings)
        self._registry = registry
        self._plan = routing_plan_from_settings(settings)

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def registry(self) -> AIProviderRegistry:
        return self._registry

    @property
    def plan(self) -> AIRoutingPlan:
        return self._plan

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        registry: AIProviderRegistry | None = None,
    ) -> AIModelRouter:
        """Create a router using environment-backed settings."""

        resolved_registry = registry
        if resolved_registry is None:
            resolved_registry = AIProviderRegistry()
            register_default_providers(resolved_registry, settings)
        return cls(settings, resolved_registry)

    def get_provider(self) -> AIProvider:
        """Return the routed provider for the current configuration."""

        try:
            primary = self._create_provider(self._plan.primary)
        except AIProviderRegistrationError:
            if self._plan.fallback is None:
                raise
            return self._create_provider(self._plan.fallback)

        if self._plan.fallback is None:
            return primary

        fallback = self._create_provider(self._plan.fallback)
        return FallbackAIProvider(primary, fallback)

    def get_provider_by_name(self, provider_name: AIProviderName) -> AIProvider:
        """Return a specific registered provider."""

        return self._create_provider(provider_name)

    def _create_provider(self, provider_name: AIProviderName) -> AIProvider:
        if not self._registry.is_registered(provider_name):
            msg = f"no provider registered for name {provider_name!r}"
            raise AIProviderRegistrationError(msg)
        return self._registry.create(provider_name)


def create_ai_model_router(
    settings: Settings,
    *,
    registry: AIProviderRegistry | None = None,
) -> AIModelRouter:
    """Create an AI model router from application settings."""

    if registry is None:
        registry = AIProviderRegistry()
        register_default_providers(registry, settings)
    return AIModelRouter(settings, registry)
