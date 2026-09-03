"""Groq AI provider implementation."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.ai.errors import AIProviderResponseError, AIProviderUnavailableError
from app.ai.provider import AIProvider
from app.ai.providers.groq.client import GroqHTTPClient, HttpxGroqClient
from app.ai.providers.groq.config import GroqProviderConfig
from app.ai.providers.groq.security import sanitize_error_message
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
from app.core.config import Settings
from app.core.metrics import track_ai_request

T = TypeVar("T", bound=BaseModel)


class GroqProvider(AIProvider):
    """AI provider backed by the Groq cloud API."""

    def __init__(
        self,
        config: GroqProviderConfig,
        *,
        client: GroqHTTPClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or HttpxGroqClient(config)

    @property
    def name(self) -> AIProviderName:
        return AIProviderName.GROQ

    @property
    def model(self) -> str:
        return self._config.model

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        async with track_ai_request(self.name.value):
            messages = _build_messages(request.prompt, request.system_prompt)
            payload = await self._client.chat_completions(
                model=self.model,
                messages=messages,
                temperature=_resolve_temperature(request.temperature, self._config),
                max_tokens=_resolve_max_tokens(request.max_tokens, self._config),
            )
            content, finish_reason, usage, model = _parse_chat_response(payload)
            return GenerateResponse(
                content=content,
                provider=self.name,
                model=model,
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
            payload = await self._client.chat_completions(
                model=self.model,
                messages=messages,
                temperature=_resolve_temperature(request.temperature, self._config),
                max_tokens=_resolve_max_tokens(request.max_tokens, self._config),
                response_format={"type": "json_object"},
            )
            content, finish_reason, usage, model = _parse_chat_response(payload)
            validated = validate_structured_output(
                extract_json_object(content),
                response_model=response_model,
            )
            return StructuredGenerateResponse(
                data=validated,
                raw_content=content,
                provider=self.name,
                model=model,
                finish_reason=finish_reason,
                usage=usage,
            )

    async def health_check(self) -> AIProviderHealthResult:
        try:
            models = await self._client.list_models()
        except (AIProviderUnavailableError, AIProviderResponseError) as exc:
            detail = sanitize_error_message(
                str(exc),
                secrets=(self._config.api_key.get_secret_value(),),
            )
            return AIProviderHealthResult(
                provider=self.name,
                healthy=False,
                detail=detail,
                model=self.model,
            )

        if self.model in models:
            return AIProviderHealthResult(
                provider=self.name,
                healthy=True,
                detail=f"groq model '{self.model}' is available",
                model=self.model,
            )

        return AIProviderHealthResult(
            provider=self.name,
            healthy=False,
            detail=f"groq model '{self.model}' is not available",
            model=self.model,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def create_groq_provider(
    settings: Settings,
    *,
    client: GroqHTTPClient | None = None,
) -> GroqProvider:
    """Create a Groq provider from application settings."""

    from app.ai.providers.groq.config import groq_provider_config_from_settings

    config = groq_provider_config_from_settings(settings)
    return GroqProvider(config, client=client)


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
    config: GroqProviderConfig,
) -> float:
    return config.default_temperature if value is None else value


def _resolve_max_tokens(
    value: int | None,
    config: GroqProviderConfig,
) -> int:
    return config.default_max_tokens if value is None else value


def _parse_chat_response(payload: dict) -> tuple[str, str | None, dict[str, int], str]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        msg = "groq chat response is missing choices"
        raise AIProviderResponseError(msg)

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        msg = "groq chat response choice must be an object"
        raise AIProviderResponseError(msg)

    message = first_choice.get("message")
    if not isinstance(message, dict):
        msg = "groq chat response is missing message content"
        raise AIProviderResponseError(msg)

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        msg = "groq chat response returned empty content"
        raise AIProviderResponseError(msg)

    finish_reason = first_choice.get("finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        finish_reason = None

    usage_payload = payload.get("usage", {})
    prompt_tokens = 0
    completion_tokens = 0
    if isinstance(usage_payload, dict):
        prompt_tokens = int(usage_payload.get("prompt_tokens") or 0)
        completion_tokens = int(usage_payload.get("completion_tokens") or 0)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }

    model = payload.get("model")
    if not isinstance(model, str) or not model:
        model = "unknown"

    return content, finish_reason, usage, model
