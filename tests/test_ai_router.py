"""Tests for the AI model router."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.ai import (
    AIModelRouter,
    AIProviderHealthResult,
    AIProviderName,
    AIProviderRegistry,
    AIProviderUnavailableError,
    FallbackAIProvider,
    GenerateRequest,
    GenerateResponse,
    StructuredGenerateRequest,
    create_ai_model_router,
    create_ollama_provider,
    is_fallback_enabled,
    resolve_provider,
    routing_plan_from_settings,
    select_fallback_provider_name,
    select_primary_provider_name,
)
from app.core.config import Settings
from tests.test_ai_provider import FakeAIProvider


class IncidentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    severity: str


def _settings(**overrides) -> Settings:
    base = {
        "_env_file": None,
        "ollama_base_url": "http://ollama:11434",
        "ollama_model_small": "llama3.2:3b",
        "ollama_model_large": "llama3.1:8b",
        "groq_api_key": "gsk_test_key",
        "groq_model": "llama-3.1-8b-instant",
    }
    base.update(overrides)
    return Settings(**base)


def _registry_with(
    *,
    ollama: FakeAIProvider | None = None,
    groq: FakeAIProvider | None = None,
) -> AIProviderRegistry:
    registry = AIProviderRegistry()
    if ollama is not None:
        registry.register(AIProviderName.OLLAMA, lambda: ollama)
    if groq is not None:
        registry.register(AIProviderName.GROQ, lambda: groq)
    return registry


def test_routing_plan_local_uses_ollama_without_fallback() -> None:
    plan = routing_plan_from_settings(_settings(ai_mode="local"))

    assert plan.ai_mode == "local"
    assert plan.primary is AIProviderName.OLLAMA
    assert plan.fallback is None
    assert plan.rca_model == "large"


def test_routing_plan_cloud_uses_groq_without_fallback() -> None:
    plan = routing_plan_from_settings(_settings(ai_mode="cloud"))

    assert plan.primary is AIProviderName.GROQ
    assert plan.fallback is None


def test_routing_plan_hybrid_enables_configured_fallback() -> None:
    plan = routing_plan_from_settings(
        _settings(ai_mode="hybrid", ai_fallback_provider="groq"),
    )

    assert plan.primary is AIProviderName.OLLAMA
    assert plan.fallback is AIProviderName.GROQ


def test_is_fallback_enabled_for_hybrid_and_explicit_flag() -> None:
    assert is_fallback_enabled(_settings(ai_mode="hybrid")) is True
    assert (
        is_fallback_enabled(_settings(ai_mode="local", ai_enable_fallback=True))
        is True
    )
    assert (
        is_fallback_enabled(_settings(ai_mode="local", ai_enable_fallback=False))
        is False
    )


def test_select_primary_and_fallback_from_settings() -> None:
    local = _settings(ai_mode="local")
    cloud = _settings(ai_mode="cloud")
    hybrid = _settings(ai_mode="hybrid", ai_fallback_provider="groq")

    assert select_primary_provider_name(local) is AIProviderName.OLLAMA
    assert select_primary_provider_name(cloud) is AIProviderName.GROQ
    assert select_primary_provider_name(hybrid) is AIProviderName.OLLAMA
    assert select_fallback_provider_name(hybrid) is AIProviderName.GROQ


def test_router_local_returns_ollama_provider() -> None:
    ollama = FakeAIProvider(name=AIProviderName.OLLAMA, model="llama3.1:8b")
    router = AIModelRouter(_settings(ai_mode="local"), _registry_with(ollama=ollama))

    provider = router.get_provider()

    assert isinstance(provider, FakeAIProvider)
    assert provider.name is AIProviderName.OLLAMA


def test_router_cloud_returns_groq_provider() -> None:
    groq = FakeAIProvider(name=AIProviderName.GROQ, model="llama-3.1-8b-instant")
    router = AIModelRouter(_settings(ai_mode="cloud"), _registry_with(groq=groq))

    provider = router.get_provider()

    assert isinstance(provider, FakeAIProvider)
    assert provider.name is AIProviderName.GROQ


def test_router_hybrid_wraps_primary_and_fallback() -> None:
    ollama = FakeAIProvider(name=AIProviderName.OLLAMA)
    groq = FakeAIProvider(name=AIProviderName.GROQ)
    router = AIModelRouter(
        _settings(ai_mode="hybrid", ai_fallback_provider="groq"),
        _registry_with(ollama=ollama, groq=groq),
    )

    provider = router.get_provider()

    assert isinstance(provider, FallbackAIProvider)
    assert provider.primary.name is AIProviderName.OLLAMA
    assert provider.fallback.name is AIProviderName.GROQ


def test_router_respects_rca_model_small_for_ollama() -> None:
    provider = create_ollama_provider(
        _settings(rca_model="small"),
    )

    assert provider.model == "llama3.2:3b"


def test_router_respects_rca_model_large_for_ollama() -> None:
    provider = create_ollama_provider(
        _settings(rca_model="large"),
    )

    assert provider.model == "llama3.1:8b"


@pytest.mark.asyncio
async def test_fallback_provider_uses_secondary_on_primary_failure() -> None:
    fallback = FakeAIProvider(
        name=AIProviderName.GROQ,
        content="fallback response",
    )

    class FailingProvider(FakeAIProvider):
        async def generate(self, request: GenerateRequest) -> GenerateResponse:
            raise AIProviderUnavailableError("primary unavailable")

    provider = FallbackAIProvider(
        FailingProvider(name=AIProviderName.OLLAMA),
        fallback,
    )

    response = await provider.generate(GenerateRequest(prompt="analyze"))

    assert response.content == "fallback response"
    assert response.provider is AIProviderName.GROQ


@pytest.mark.asyncio
async def test_fallback_provider_structured_generate_uses_secondary() -> None:
    fallback = FakeAIProvider(name=AIProviderName.GROQ)

    class FailingProvider(FakeAIProvider):
        async def generate(self, request: GenerateRequest) -> GenerateResponse:
            raise AIProviderUnavailableError("primary unavailable")

    provider = FallbackAIProvider(
        FailingProvider(name=AIProviderName.OLLAMA),
        fallback,
    )

    response = await provider.structured_generate(
        StructuredGenerateRequest(prompt="summarize"),
        response_model=IncidentSummary,
    )

    assert response.data["title"] == "Checkout outage"
    assert response.provider is AIProviderName.GROQ


@pytest.mark.asyncio
async def test_fallback_health_check_uses_secondary_when_primary_unhealthy() -> None:
    class UnhealthyProvider(FakeAIProvider):
        async def health_check(self) -> AIProviderHealthResult:
            return AIProviderHealthResult(
                provider=self.name,
                healthy=False,
                detail="primary down",
                model=self.model,
            )

    provider = FallbackAIProvider(
        UnhealthyProvider(name=AIProviderName.OLLAMA),
        FakeAIProvider(name=AIProviderName.GROQ, healthy=True),
    )

    result = await provider.health_check()

    assert result.healthy is True
    assert result.provider is AIProviderName.GROQ


def test_resolve_provider_uses_fallback_when_primary_missing() -> None:
    settings = _settings(
        ai_mode="local",
        ai_enable_fallback=True,
        ai_fallback_provider="groq",
    )
    registry = _registry_with(
        groq=FakeAIProvider(name=AIProviderName.GROQ),
    )

    provider = resolve_provider(settings, registry)

    assert provider.name is AIProviderName.GROQ


def test_create_ai_model_router_from_settings() -> None:
    router = create_ai_model_router(_settings(ai_mode="cloud"))

    assert router.plan.primary is AIProviderName.GROQ
