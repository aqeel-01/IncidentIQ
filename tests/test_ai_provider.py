"""Provider-independent tests for the AI provider abstraction."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.ai import (
    AIProvider,
    AIProviderHealthResult,
    AIProviderName,
    AIProviderRegistrationError,
    AIProviderRegistry,
    AIProviderResponseError,
    AIProviderStructuredOutputError,
    GenerateRequest,
    GenerateResponse,
    StructuredGenerateRequest,
    resolve_provider,
    select_fallback_provider_name,
    select_primary_provider_name,
)
from app.ai.structured import extract_json_object, validate_structured_output
from app.core.config import Settings


class IncidentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    severity: str


class FakeAIProvider(AIProvider):
    """In-memory provider used to test the abstraction without vendor SDKs."""

    def __init__(
        self,
        *,
        name: AIProviderName = AIProviderName.OLLAMA,
        model: str = "fake-model",
        content: str = "analysis complete",
        structured_payload: dict | None = None,
        healthy: bool = True,
        health_detail: str = "fake provider ready",
    ) -> None:
        self._name = name
        self._model = model
        self._content = content
        self._structured_payload = structured_payload or {
            "title": "Checkout outage",
            "severity": "high",
        }
        self._healthy = healthy
        self._health_detail = health_detail
        self.generate_calls: list[GenerateRequest] = []

    @property
    def name(self) -> AIProviderName:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.generate_calls.append(request)
        content = self._content
        if (
            self._structured_payload is not None
            and "Respond with valid JSON only" in request.prompt
        ):
            content = json.dumps(self._structured_payload)
        return GenerateResponse(
            content=content,
            provider=self._name,
            model=self._model,
            finish_reason="stop",
            usage={"prompt_tokens": 12, "completion_tokens": 8},
        )

    async def health_check(self) -> AIProviderHealthResult:
        return AIProviderHealthResult(
            provider=self._name,
            healthy=self._healthy,
            detail=self._health_detail,
            model=self._model,
            checked_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        )


class ParsingProvider(AIProvider):
    """Minimal provider that returns JSON for base structured generation tests."""

    @property
    def name(self) -> AIProviderName:
        return AIProviderName.OLLAMA

    @property
    def model(self) -> str:
        return "parsing-model"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        return GenerateResponse(
            content='{"title": "API latency", "severity": "medium"}',
            provider=self.name,
            model=self.model,
        )

    async def health_check(self) -> AIProviderHealthResult:
        return AIProviderHealthResult(
            provider=self.name,
            healthy=True,
            detail="ready",
            model=self.model,
        )


def _registry_with_fake(
    *,
    name: AIProviderName = AIProviderName.OLLAMA,
    provider: FakeAIProvider | None = None,
) -> AIProviderRegistry:
    registry = AIProviderRegistry()
    instance = provider or FakeAIProvider(name=name)
    registry.register(name, lambda: instance)
    return registry


@pytest.mark.asyncio
async def test_generate_returns_provider_metadata() -> None:
    provider = FakeAIProvider(
        name=AIProviderName.GROQ,
        model="llama-3.1-8b",
        content="root cause identified",
    )

    response = await provider.generate(
        GenerateRequest(prompt="analyze incident", temperature=0.2, max_tokens=256)
    )

    assert response.content == "root cause identified"
    assert response.provider is AIProviderName.GROQ
    assert response.model == "llama-3.1-8b"
    assert response.finish_reason == "stop"
    assert response.usage["completion_tokens"] == 8
    assert provider.generate_calls[0].prompt == "analyze incident"


@pytest.mark.asyncio
async def test_structured_generate_validates_response_model() -> None:
    provider = FakeAIProvider()

    response = await provider.structured_generate(
        StructuredGenerateRequest(prompt="summarize incident"),
        response_model=IncidentSummary,
    )

    assert response.data == {"title": "Checkout outage", "severity": "high"}
    assert response.provider is AIProviderName.OLLAMA
    assert response.model == "fake-model"


@pytest.mark.asyncio
async def test_health_check_reports_provider_state() -> None:
    healthy = await FakeAIProvider(healthy=True).health_check()
    unhealthy = await FakeAIProvider(
        healthy=False,
        health_detail="connection refused",
    ).health_check()

    assert healthy.healthy is True
    assert healthy.provider is AIProviderName.OLLAMA
    assert unhealthy.healthy is False
    assert unhealthy.detail == "connection refused"


def test_registry_rejects_duplicate_registration() -> None:
    registry = AIProviderRegistry()
    registry.register(AIProviderName.OLLAMA, lambda: FakeAIProvider())

    with pytest.raises(AIProviderRegistrationError):
        registry.register(AIProviderName.OLLAMA, lambda: FakeAIProvider())


def test_registry_create_unknown_provider_raises() -> None:
    registry = AIProviderRegistry()

    with pytest.raises(AIProviderRegistrationError):
        registry.create(AIProviderName.GROQ)


@pytest.mark.asyncio
async def test_base_structured_generate_parses_json_from_generate() -> None:
    response = await ParsingProvider().structured_generate(
        StructuredGenerateRequest(prompt="summarize"),
        response_model=IncidentSummary,
    )

    assert response.data["title"] == "API latency"
    assert response.data["severity"] == "medium"


def test_extract_json_object_supports_fenced_json_blocks() -> None:
    payload = extract_json_object(
        'Here is the result:\n```json\n{"title": "x", "severity": "low"}\n```'
    )

    assert payload == {"title": "x", "severity": "low"}


def test_validate_structured_output_rejects_invalid_payload() -> None:
    with pytest.raises(AIProviderStructuredOutputError):
        validate_structured_output(
            {"title": "", "severity": "low"},
            response_model=IncidentSummary,
        )


def test_extract_json_object_raises_on_empty_content() -> None:
    with pytest.raises(AIProviderResponseError):
        extract_json_object("   ")


def test_select_primary_provider_name_from_settings() -> None:
    local = Settings(_env_file=None, ai_mode="local")
    cloud = Settings(_env_file=None, ai_mode="cloud")
    hybrid = Settings(_env_file=None, ai_mode="hybrid")

    assert select_primary_provider_name(local) is AIProviderName.OLLAMA
    assert select_primary_provider_name(cloud) is AIProviderName.GROQ
    assert select_primary_provider_name(hybrid) is AIProviderName.OLLAMA


def test_select_fallback_provider_name_from_settings() -> None:
    settings = Settings(_env_file=None, ai_fallback_provider="groq")
    assert select_fallback_provider_name(settings) is AIProviderName.GROQ


def test_resolve_provider_uses_registered_primary() -> None:
    settings = Settings(_env_file=None, ai_mode="local")
    registry = _registry_with_fake(name=AIProviderName.OLLAMA)

    provider = resolve_provider(settings, registry)

    assert isinstance(provider, FakeAIProvider)
    assert provider.name is AIProviderName.OLLAMA


def test_resolve_provider_uses_fallback_when_primary_missing() -> None:
    settings = Settings(
        _env_file=None,
        ai_mode="local",
        ai_enable_fallback=True,
        ai_fallback_provider="groq",
    )
    registry = AIProviderRegistry()
    registry.register(
        AIProviderName.GROQ,
        lambda: FakeAIProvider(name=AIProviderName.GROQ),
    )

    provider = resolve_provider(settings, registry)

    assert provider.name is AIProviderName.GROQ


def test_resolve_provider_raises_when_no_provider_registered() -> None:
    settings = Settings(_env_file=None, ai_mode="cloud")

    with pytest.raises(AIProviderRegistrationError):
        resolve_provider(settings, AIProviderRegistry())
