"""HTTP client for the Ollama API."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.ai.errors import AIProviderResponseError, AIProviderUnavailableError
from app.ai.providers.ollama.config import OllamaProviderConfig


class OllamaHTTPClient(Protocol):
    """Minimal HTTP surface used by :class:`OllamaProvider`."""

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def list_models(self) -> list[str]: ...

    async def aclose(self) -> None: ...


class HttpxOllamaClient:
    """Async Ollama HTTP client backed by ``httpx``."""

    def __init__(self, config: OllamaProviderConfig) -> None:
        self._timeout_seconds = config.timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=config.normalized_base_url,
            timeout=config.timeout_seconds,
        )

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options
        if response_format is not None:
            payload["format"] = response_format

        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = f"ollama request timed out after {self._timeout_seconds} seconds"
            raise AIProviderUnavailableError(msg) from exc
        except httpx.HTTPError as exc:
            msg = f"ollama request failed: {exc}"
            raise AIProviderUnavailableError(msg) from exc

        data = response.json()
        if not isinstance(data, dict):
            msg = "ollama chat response must be a JSON object"
            raise AIProviderResponseError(msg)
        return data

    async def list_models(self) -> list[str]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = f"ollama tags request timed out after {self._timeout_seconds} seconds"
            raise AIProviderUnavailableError(msg) from exc
        except httpx.HTTPError as exc:
            msg = f"ollama tags request failed: {exc}"
            raise AIProviderUnavailableError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            msg = "ollama tags response must be a JSON object"
            raise AIProviderResponseError(msg)

        models = payload.get("models", [])
        if not isinstance(models, list):
            msg = "ollama tags response models must be a list"
            raise AIProviderResponseError(msg)

        names: list[str] = []
        for item in models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(item["name"])
        return names

    async def aclose(self) -> None:
        await self._client.aclose()
