"""AI provider factory registry."""

from __future__ import annotations

from collections.abc import Callable

from app.ai.errors import AIProviderRegistrationError
from app.ai.provider import AIProvider
from app.ai.types import AIProviderName

AIProviderFactory = Callable[[], AIProvider]


class AIProviderRegistry:
    """Register and instantiate AI provider implementations by name."""

    def __init__(self) -> None:
        self._factories: dict[AIProviderName, AIProviderFactory] = {}

    def register(
        self,
        provider_name: AIProviderName,
        factory: AIProviderFactory,
        *,
        replace: bool = False,
    ) -> None:
        if provider_name in self._factories and not replace:
            msg = f"provider {provider_name!r} is already registered"
            raise AIProviderRegistrationError(msg)
        self._factories[provider_name] = factory

    def create(self, provider_name: AIProviderName) -> AIProvider:
        factory = self._factories.get(provider_name)
        if factory is None:
            msg = f"no provider registered for name {provider_name!r}"
            raise AIProviderRegistrationError(msg)
        return factory()

    def is_registered(self, provider_name: AIProviderName) -> bool:
        return provider_name in self._factories

    def supported_providers(self) -> frozenset[AIProviderName]:
        return frozenset(self._factories)
