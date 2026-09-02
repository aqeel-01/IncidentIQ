"""Tests for the Groq AI provider."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.ai import (
    AIProviderConfigurationError,
    AIProviderName,
    AIProviderResponseError,
    AIProviderStructuredOutputError,
    AIProviderUnavailableError,
    GenerateRequest,
    StructuredGenerateRequest,
    create_groq_provider,
    default_ai_provider_registry,
    groq_provider_config_from_settings,
)
from app.ai.providers.groq.client import HttpxGroqClient, build_auth_headers
from app.ai.providers.groq.config import GroqProviderConfig
from app.ai.providers.groq.provider import GroqProvider
from app.ai.providers.groq.security import sanitize_error_message
from app.core.config import Settings

_SECRET_API_KEY = "gsk_supersecret_api_key_value_12345"


class IncidentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    severity: str


CHAT_RESPONSE = {
    "id": "chatcmpl-test",
    "model": "llama-3.1-8b-instant",
    "choices": [
        {
            "message": {"role": "assistant", "content": "root cause identified"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}

STRUCTURED_CHAT_RESPONSE = {
    "id": "chatcmpl-test",
    "model": "llama-3.1-8b-instant",
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {"title": "Checkout outage", "severity": "high"},
                ),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 20, "completion_tokens": 12, "total_tokens": 32},
}

MODELS_RESPONSE = {
    "object": "list",
    "data": [
        {"id": "llama-3.1-8b-instant", "object": "model"},
        {"id": "llama-3.3-70b-versatile", "object": "model"},
    ],
}


def _settings(**overrides) -> Settings:
    base = {
        "_env_file": None,
        "groq_api_key": _SECRET_API_KEY,
        "groq_model": "llama-3.1-8b-instant",
        "groq_timeout_seconds": 30.0,
    }
    base.update(overrides)
    return Settings(**base)


def _config(**overrides) -> GroqProviderConfig:
    return groq_provider_config_from_settings(_settings(**overrides))


class FakeGroqAsyncClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self.get_calls: list[str] = []
        self.chat_response = CHAT_RESPONSE
        self.models_response = MODELS_RESPONSE
        self.post_error: Exception | None = None
        self.get_error: Exception | None = None

    async def post(self, path: str, **kwargs: object):
        self.post_calls.append((path, kwargs))
        if self.post_error is not None:
            raise self.post_error
        request = httpx.Request(
            "POST",
            f"https://api.groq.com/openai/v1{path}",
        )
        return httpx.Response(200, json=self.chat_response, request=request)

    async def get(self, path: str, **kwargs: object):
        self.get_calls.append(path)
        if self.get_error is not None:
            raise self.get_error
        request = httpx.Request(
            "GET",
            f"https://api.groq.com/openai/v1{path}",
        )
        return httpx.Response(200, json=self.models_response, request=request)

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeGroqAsyncClient:
    fake = FakeGroqAsyncClient()

    def _factory(**kwargs: object) -> FakeGroqAsyncClient:
        fake.kwargs.update(kwargs)
        return fake

    monkeypatch.setattr(
        "app.ai.providers.groq.client.httpx.AsyncClient",
        _factory,
    )
    return fake


def test_config_requires_api_key_and_model() -> None:
    with pytest.raises(AIProviderConfigurationError, match="GROQ_API_KEY"):
        groq_provider_config_from_settings(_settings(groq_api_key=""))

    with pytest.raises(AIProviderConfigurationError, match="GROQ_MODEL"):
        groq_provider_config_from_settings(_settings(groq_model=""))


def test_config_repr_does_not_expose_api_key() -> None:
    rendered = repr(_config())

    assert _SECRET_API_KEY not in rendered
    assert "SecretStr" in rendered or "**********" in rendered


def test_build_auth_headers_uses_bearer_token() -> None:
    headers = build_auth_headers(_config())

    assert headers["Authorization"] == f"Bearer {_SECRET_API_KEY}"
    assert "Content-Type" in headers


def test_sanitize_error_message_redacts_api_keys() -> None:
    message = (
        "request failed with Authorization: Bearer "
        f"{_SECRET_API_KEY} and key {_SECRET_API_KEY}"
    )

    sanitized = sanitize_error_message(message, secrets=(_SECRET_API_KEY,))

    assert _SECRET_API_KEY not in sanitized
    assert "Bearer ***" in sanitized


@pytest.mark.asyncio
async def test_generate_uses_configured_model(
    fake_client: FakeGroqAsyncClient,
) -> None:
    provider = GroqProvider(_config())

    response = await provider.generate(
        GenerateRequest(prompt="analyze incident", temperature=0.2, max_tokens=128)
    )

    assert response.content == "root cause identified"
    assert response.provider is AIProviderName.GROQ
    assert response.model == "llama-3.1-8b-instant"
    assert response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 11, "completion_tokens": 7}

    payload = fake_client.post_calls[0][1]["json"]
    assert payload["model"] == "llama-3.1-8b-instant"
    assert payload["messages"][-1]["content"] == "analyze incident"
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 128


@pytest.mark.asyncio
async def test_structured_generate_requests_json_object_format(
    fake_client: FakeGroqAsyncClient,
) -> None:
    fake_client.chat_response = STRUCTURED_CHAT_RESPONSE
    provider = GroqProvider(_config())

    response = await provider.structured_generate(
        StructuredGenerateRequest(prompt="summarize incident"),
        response_model=IncidentSummary,
    )

    assert response.data == {"title": "Checkout outage", "severity": "high"}
    payload = fake_client.post_calls[0][1]["json"]
    assert payload["response_format"] == {"type": "json_object"}
    assert "Respond with valid JSON only" in payload["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_health_check_reports_available_model(
    fake_client: FakeGroqAsyncClient,
) -> None:
    provider = GroqProvider(_config())

    result = await provider.health_check()

    assert result.healthy is True
    assert result.model == "llama-3.1-8b-instant"
    assert _SECRET_API_KEY not in result.detail
    assert fake_client.get_calls == ["/models"]


@pytest.mark.asyncio
async def test_health_check_reports_missing_model(
    fake_client: FakeGroqAsyncClient,
) -> None:
    fake_client.models_response = {
        "object": "list",
        "data": [{"id": "llama-3.3-70b-versatile", "object": "model"}],
    }
    provider = GroqProvider(_config())

    result = await provider.health_check()

    assert result.healthy is False
    assert "not available" in result.detail


@pytest.mark.asyncio
async def test_generate_raises_on_timeout(fake_client: FakeGroqAsyncClient) -> None:
    fake_client.post_error = httpx.TimeoutException("timed out")
    provider = GroqProvider(_config())

    with pytest.raises(AIProviderUnavailableError, match="timed out") as exc_info:
        await provider.generate(GenerateRequest(prompt="analyze"))

    assert _SECRET_API_KEY not in str(exc_info.value)


@pytest.mark.asyncio
async def test_generate_raises_on_connection_failure(
    fake_client: FakeGroqAsyncClient,
) -> None:
    fake_client.post_error = httpx.ConnectError(
        f"connection refused for Bearer {_SECRET_API_KEY}"
    )
    provider = GroqProvider(_config())

    with pytest.raises(AIProviderUnavailableError, match="connection refused") as exc:
        await provider.generate(GenerateRequest(prompt="analyze"))

    assert _SECRET_API_KEY not in str(exc.value)


@pytest.mark.asyncio
async def test_generate_raises_on_empty_response(
    fake_client: FakeGroqAsyncClient,
) -> None:
    fake_client.chat_response = {
        "model": "llama-3.1-8b-instant",
        "choices": [{"message": {"role": "assistant", "content": "   "}}],
    }
    provider = GroqProvider(_config())

    with pytest.raises(AIProviderResponseError, match="empty content"):
        await provider.generate(GenerateRequest(prompt="analyze"))


@pytest.mark.asyncio
async def test_structured_generate_raises_on_invalid_json(
    fake_client: FakeGroqAsyncClient,
) -> None:
    fake_client.chat_response = {
        "model": "llama-3.1-8b-instant",
        "choices": [{"message": {"role": "assistant", "content": "not-json"}}],
    }
    provider = GroqProvider(_config())

    with pytest.raises(AIProviderStructuredOutputError):
        await provider.structured_generate(
            StructuredGenerateRequest(prompt="summarize"),
            response_model=IncidentSummary,
        )


@pytest.mark.asyncio
async def test_health_check_redacts_api_key_from_connection_errors(
    fake_client: FakeGroqAsyncClient,
) -> None:
    fake_client.get_error = httpx.ConnectError(
        f"connection refused for Bearer {_SECRET_API_KEY}"
    )
    provider = GroqProvider(_config())

    result = await provider.health_check()

    assert result.healthy is False
    assert _SECRET_API_KEY not in result.detail


def test_default_registry_registers_groq_provider() -> None:
    registry = default_ai_provider_registry(_settings())
    provider = registry.create(AIProviderName.GROQ)

    assert isinstance(provider, GroqProvider)
    assert provider.model == "llama-3.1-8b-instant"


def test_httpx_client_uses_configured_base_url_and_timeout() -> None:
    config = GroqProviderConfig(
        api_key=SecretStr(_SECRET_API_KEY),
        model="llama-3.1-8b-instant",
        timeout_seconds=30.0,
    )
    client = HttpxGroqClient(config)

    assert client._timeout_seconds == 30.0
    assert str(client._client.base_url).rstrip("/") == "https://api.groq.com/openai/v1"
    assert _SECRET_API_KEY not in repr(client)


def test_create_groq_provider_from_settings() -> None:
    provider = create_groq_provider(_settings())

    assert isinstance(provider, GroqProvider)
    assert provider.model == "llama-3.1-8b-instant"
