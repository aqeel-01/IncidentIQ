"""HTTP client for the Groq API."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.ai.errors import AIProviderResponseError, AIProviderUnavailableError
from app.ai.providers.groq.config import GroqProviderConfig
from app.ai.providers.groq.security import sanitize_error_message


class GroqHTTPClient(Protocol):
    """Minimal HTTP surface used by :class:`GroqProvider`."""

    async def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    async def list_models(self) -> list[str]: ...

    async def aclose(self) -> None: ...


def build_auth_headers(config: GroqProviderConfig) -> dict[str, str]:
    """Build Groq API headers without logging credential values."""

    return {
        "Authorization": f"Bearer {config.api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }


class HttpxGroqClient:
    """Async Groq HTTP client backed by ``httpx``."""

    def __init__(self, config: GroqProviderConfig) -> None:
        self._config = config
        self._timeout_seconds = config.timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=config.normalized_base_url,
            headers=build_auth_headers(config),
            timeout=config.timeout_seconds,
        )

    async def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = f"groq request timed out after {self._timeout_seconds} seconds"
            raise AIProviderUnavailableError(msg) from exc
        except httpx.HTTPError as exc:
            msg = sanitize_error_message(
                f"groq request failed: {exc}",
                secrets=(self._config.api_key.get_secret_value(),),
            )
            raise AIProviderUnavailableError(msg) from exc

        data = response.json()
        if not isinstance(data, dict):
            msg = "groq chat response must be a JSON object"
            raise AIProviderResponseError(msg)
        return data

    async def list_models(self) -> list[str]:
        try:
            response = await self._client.get("/models")
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = f"groq models request timed out after {self._timeout_seconds} seconds"
            raise AIProviderUnavailableError(msg) from exc
        except httpx.HTTPError as exc:
            msg = sanitize_error_message(
                f"groq models request failed: {exc}",
                secrets=(self._config.api_key.get_secret_value(),),
            )
            raise AIProviderUnavailableError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            msg = "groq models response must be a JSON object"
            raise AIProviderResponseError(msg)

        models = payload.get("data", [])
        if not isinstance(models, list):
            msg = "groq models response data must be a list"
            raise AIProviderResponseError(msg)

        names: list[str] = []
        for item in models:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                names.append(item["id"])
        return names

    async def aclose(self) -> None:
        await self._client.aclose()
