"""Ollama AI provider implementation."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.ai.errors import AIProviderResponseError, AIProviderUnavailableError
from app.ai.provider import AIProvider
from app.ai.providers.ollama.client import HttpxOllamaClient, OllamaHTTPClient
from app.ai.providers.ollama.config import OllamaProviderConfig
from app.ai.structured import (
    build_structured_prompt,
    extract_json_object,
    validate_structured_output,
)
from app.ai.types import (
    AIProviderHealthResult,
    AIProviderName,
    GenerateRequest,
    GenerateResponse,
    StructuredGenerateRequest,
    StructuredGenerateResponse,
)
from app.core.config import RCAModelSize, Settings
from app.core.metrics import track_ai_request

T = TypeVar("T", bound=BaseModel)


class OllamaProvider(AIProvider):
    """AI provider backed by a local or remote Ollama server."""

    def __init__(
        self,
        config: OllamaProviderConfig,
        *,
        client: OllamaHTTPClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or HttpxOllamaClient(config)

    @property
    def name(self) -> AIProviderName:
        return AIProviderName.OLLAMA

    @property
    def model(self) -> str:
        return self._config.active_model

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        async with track_ai_request(self.name.value):
            messages = _build_messages(request.prompt, request.system_prompt)
            payload = await self._client.chat(
                model=self.model,
                messages=messages,
                temperature=_resolve_temperature(request.temperature, self._config),
                max_tokens=_resolve_max_tokens(request.max_tokens, self._config),
            )
            content, finish_reason, usage = _parse_chat_response(payload)
            return GenerateResponse(
                content=content,
                provider=self.name,
                model=self.model,
                finish_reason=finish_reason,
                usage=usage,
            )

    async def structured_generate(
        self,
        request: StructuredGenerateRequest,
        *,
        response_model: type[T],
    ) -> StructuredGenerateResponse:
        async with track_ai_request(self.name.value):
            prompt = build_structured_prompt(
                request.prompt,
                response_model=response_model,
            )
            messages = _build_messages(prompt, request.system_prompt)
            payload = await self._client.chat(
                model=self.model,
                messages=messages,
                temperature=_resolve_temperature(request.temperature, self._config),
                max_tokens=_resolve_max_tokens(request.max_tokens, self._config),
                response_format="json",
            )
            content, finish_reason, usage = _parse_chat_response(payload)
            validated = validate_structured_output(
                extract_json_object(content),
                response_model=response_model,
            )
            return StructuredGenerateResponse(
                data=validated,
                raw_content=content,
                provider=self.name,
                model=self.model,
                finish_reason=finish_reason,
                usage=usage,
            )

    async def health_check(self) -> AIProviderHealthResult:
        try:
            models = await self._client.list_models()
        except (AIProviderUnavailableError, AIProviderResponseError) as exc:
            return AIProviderHealthResult(
                provider=self.name,
                healthy=False,
                detail=str(exc),
                model=self.model,
            )

        if self.model in models:
            return AIProviderHealthResult(
                provider=self.name,
                healthy=True,
                detail=f"ollama model '{self.model}' is available",
                model=self.model,
            )

        return AIProviderHealthResult(
            provider=self.name,
            healthy=False,
            detail=f"ollama model '{self.model}' is not available",
            model=self.model,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def create_ollama_provider(
    settings: Settings,
    *,
    model_size: RCAModelSize | None = None,
    client: OllamaHTTPClient | None = None,
) -> OllamaProvider:
    """Create an Ollama provider from application settings."""

    from app.ai.providers.ollama.config import ollama_provider_config_from_settings

    config = ollama_provider_config_from_settings(
        settings,
        model_size=model_size,
    )
    return OllamaProvider(config, client=client)


def _build_messages(
    prompt: str,
    system_prompt: str | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return messages


def _resolve_temperature(
    value: float | None,
    config: OllamaProviderConfig,
) -> float:
    return config.default_temperature if value is None else value


def _resolve_max_tokens(
    value: int | None,
    config: OllamaProviderConfig,
) -> int:
    return config.default_max_tokens if value is None else value


def _parse_chat_response(payload: dict) -> tuple[str, str | None, dict[str, int]]:
    message = payload.get("message")
    if not isinstance(message, dict):
        msg = "ollama chat response is missing message content"
        raise AIProviderResponseError(msg)

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        msg = "ollama chat response returned empty content"
        raise AIProviderResponseError(msg)

    finish_reason = payload.get("done_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        finish_reason = None

    usage = {
        "prompt_tokens": int(payload.get("prompt_eval_count") or 0),
        "completion_tokens": int(payload.get("eval_count") or 0),
    }
    return content, finish_reason, usage
