"""Tests for the Ollama AI provider."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.ai import (
    AIProviderConfigurationError,
    AIProviderName,
    AIProviderResponseError,
    AIProviderStructuredOutputError,
    AIProviderUnavailableError,
    GenerateRequest,
    StructuredGenerateRequest,
    create_ollama_provider,
    default_ai_provider_registry,
    ollama_provider_config_from_settings,
)
from app.ai.providers.ollama.client import HttpxOllamaClient
from app.ai.providers.ollama.config import (
    OllamaProviderConfig,
    resolve_ollama_model_name,
)
from app.ai.providers.ollama.provider import OllamaProvider
from app.core.config import Settings


class IncidentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    severity: str


CHAT_RESPONSE = {
    "model": "llama3.2:3b",
    "message": {"role": "assistant", "content": "root cause identified"},
    "done": True,
    "done_reason": "stop",
    "prompt_eval_count": 11,
    "eval_count": 7,
}

STRUCTURED_CHAT_RESPONSE = {
    "model": "llama3.2:3b",
    "message": {
        "role": "assistant",
        "content": json.dumps(
            {"title": "Checkout outage", "severity": "high"},
        ),
    },
    "done": True,
    "done_reason": "stop",
    "prompt_eval_count": 20,
    "eval_count": 12,
}

TAGS_RESPONSE = {
    "models": [
        {"name": "llama3.2:3b"},
        {"name": "llama3.1:8b"},
    ]
}


def _settings(**overrides) -> Settings:
    base = {
        "_env_file": None,
        "ollama_base_url": "http://ollama:11434",
        "ollama_model_small": "llama3.2:3b",
        "ollama_model_large": "llama3.1:8b",
        "rca_model": "large",
        "ollama_timeout_seconds": 30.0,
    }
    base.update(overrides)
    return Settings(**base)


def _config(**overrides) -> OllamaProviderConfig:
    return ollama_provider_config_from_settings(_settings(**overrides))


class FakeOllamaAsyncClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self.get_calls: list[str] = []
        self.chat_response = CHAT_RESPONSE
        self.tags_response = TAGS_RESPONSE
        self.post_error: Exception | None = None
        self.get_error: Exception | None = None

    async def post(self, path: str, **kwargs: object):
        self.post_calls.append((path, kwargs))
        if self.post_error is not None:
            raise self.post_error
        request = httpx.Request("POST", f"http://ollama:11434{path}")
        return httpx.Response(200, json=self.chat_response, request=request)

    async def get(self, path: str, **kwargs: object):
        self.get_calls.append(path)
        if self.get_error is not None:
            raise self.get_error
        request = httpx.Request("GET", f"http://ollama:11434{path}")
        return httpx.Response(200, json=self.tags_response, request=request)

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeOllamaAsyncClient:
    fake = FakeOllamaAsyncClient()

    def _factory(**kwargs: object) -> FakeOllamaAsyncClient:
        fake.kwargs.update(kwargs)
        return fake

    monkeypatch.setattr(
        "app.ai.providers.ollama.client.httpx.AsyncClient",
        _factory,
    )
    return fake


def test_config_resolves_small_and_large_models() -> None:
    config = _config(rca_model="small")
    assert resolve_ollama_model_name(config, "small") == "llama3.2:3b"
    assert resolve_ollama_model_name(config, "large") == "llama3.1:8b"
    assert config.active_model == "llama3.2:3b"


def test_config_raises_when_model_name_missing() -> None:
    config = _config(ollama_model_small="", rca_model="small")
    with pytest.raises(AIProviderConfigurationError):
        _ = config.active_model


@pytest.mark.asyncio
async def test_generate_uses_configured_large_model(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    provider = OllamaProvider(_config())

    response = await provider.generate(
        GenerateRequest(prompt="analyze incident", temperature=0.2, max_tokens=128)
    )

    assert response.content == "root cause identified"
    assert response.provider is AIProviderName.OLLAMA
    assert response.model == "llama3.1:8b"
    assert response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 11, "completion_tokens": 7}

    payload = fake_client.post_calls[0][1]["json"]
    assert payload["model"] == "llama3.1:8b"
    assert payload["messages"][-1]["content"] == "analyze incident"
    assert payload["options"]["temperature"] == 0.2
    assert payload["options"]["num_predict"] == 128


@pytest.mark.asyncio
async def test_generate_uses_small_model_when_configured(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    provider = create_ollama_provider(_settings(rca_model="small"))

    response = await provider.generate(GenerateRequest(prompt="summarize"))

    assert response.model == "llama3.2:3b"
    payload = fake_client.post_calls[0][1]["json"]
    assert payload["model"] == "llama3.2:3b"


@pytest.mark.asyncio
async def test_structured_generate_requests_json_format(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    fake_client.chat_response = STRUCTURED_CHAT_RESPONSE
    provider = OllamaProvider(_config())

    response = await provider.structured_generate(
        StructuredGenerateRequest(prompt="summarize incident"),
        response_model=IncidentSummary,
    )

    assert response.data == {"title": "Checkout outage", "severity": "high"}
    payload = fake_client.post_calls[0][1]["json"]
    assert payload["format"] == "json"
    assert "Respond with valid JSON only" in payload["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_health_check_reports_available_model(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    provider = OllamaProvider(_config())

    result = await provider.health_check()

    assert result.healthy is True
    assert result.model == "llama3.1:8b"
    assert fake_client.get_calls == ["/api/tags"]


@pytest.mark.asyncio
async def test_health_check_reports_missing_model(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    fake_client.tags_response = {"models": [{"name": "llama3.2:3b"}]}
    provider = OllamaProvider(_config())

    result = await provider.health_check()

    assert result.healthy is False
    assert "not available" in result.detail


@pytest.mark.asyncio
async def test_generate_raises_on_timeout(fake_client: FakeOllamaAsyncClient) -> None:
    fake_client.post_error = httpx.TimeoutException("timed out")
    provider = OllamaProvider(_config())

    with pytest.raises(AIProviderUnavailableError, match="timed out"):
        await provider.generate(GenerateRequest(prompt="analyze"))


@pytest.mark.asyncio
async def test_generate_raises_on_connection_failure(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    fake_client.post_error = httpx.ConnectError("connection refused")
    provider = OllamaProvider(_config())

    with pytest.raises(AIProviderUnavailableError, match="connection refused"):
        await provider.generate(GenerateRequest(prompt="analyze"))


@pytest.mark.asyncio
async def test_generate_raises_on_empty_response(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    fake_client.chat_response = {
        "model": "llama3.1:8b",
        "message": {"role": "assistant", "content": "   "},
        "done": True,
    }
    provider = OllamaProvider(_config())

    with pytest.raises(AIProviderResponseError, match="empty content"):
        await provider.generate(GenerateRequest(prompt="analyze"))


@pytest.mark.asyncio
async def test_structured_generate_raises_on_invalid_json(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    fake_client.chat_response = {
        "model": "llama3.1:8b",
        "message": {"role": "assistant", "content": "not-json"},
        "done": True,
    }
    provider = OllamaProvider(_config())

    with pytest.raises(AIProviderStructuredOutputError):
        await provider.structured_generate(
            StructuredGenerateRequest(prompt="summarize"),
            response_model=IncidentSummary,
        )


@pytest.mark.asyncio
async def test_health_check_returns_unhealthy_on_connection_failure(
    fake_client: FakeOllamaAsyncClient,
) -> None:
    fake_client.get_error = httpx.ConnectError("connection refused")
    provider = OllamaProvider(_config())

    result = await provider.health_check()

    assert result.healthy is False
    assert "connection refused" in result.detail


def test_default_registry_registers_ollama_provider() -> None:
    registry = default_ai_provider_registry(_settings())
    provider = registry.create(AIProviderName.OLLAMA)

    assert isinstance(provider, OllamaProvider)
    assert provider.model == "llama3.1:8b"


def test_httpx_client_uses_configured_base_url_and_timeout() -> None:
    config = _config()
    client = HttpxOllamaClient(config)

    assert client._timeout_seconds == 30.0
    assert client._client.base_url == "http://ollama:11434"
