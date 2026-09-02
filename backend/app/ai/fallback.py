"""Fallback wrapper for AI providers."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.ai.errors import AIProviderUnavailableError
from app.ai.provider import AIProvider
from app.ai.types import (
    AIProviderHealthResult,
    AIProviderName,
    GenerateRequest,
    GenerateResponse,
    StructuredGenerateRequest,
    StructuredGenerateResponse,
)

T = TypeVar("T", bound=BaseModel)


class FallbackAIProvider(AIProvider):
    """Try a primary provider and fall back when it is unavailable."""

    def __init__(
        self,
        primary: AIProvider,
        fallback: AIProvider,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def primary(self) -> AIProvider:
        return self._primary

    @property
    def fallback(self) -> AIProvider:
        return self._fallback

    @property
    def name(self) -> AIProviderName:
        return self._primary.name

    @property
    def model(self) -> str:
        return self._primary.model

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        try:
            return await self._primary.generate(request)
        except AIProviderUnavailableError:
            return await self._fallback.generate(request)

    async def structured_generate(
        self,
        request: StructuredGenerateRequest,
        *,
        response_model: type[T],
    ) -> StructuredGenerateResponse:
        try:
            return await self._primary.structured_generate(
                request,
                response_model=response_model,
            )
        except AIProviderUnavailableError:
            return await self._fallback.structured_generate(
                request,
                response_model=response_model,
            )

    async def health_check(self) -> AIProviderHealthResult:
        primary_result = await self._primary.health_check()
        if primary_result.healthy:
            return primary_result

        fallback_result = await self._fallback.health_check()
        if fallback_result.healthy:
            return fallback_result

        return AIProviderHealthResult(
            provider=self.name,
            healthy=False,
            detail=(
                f"primary unavailable ({primary_result.detail}); "
                f"fallback unavailable ({fallback_result.detail})"
            ),
            model=self.model,
        )

    async def aclose(self) -> None:
        await self._primary.aclose()
        await self._fallback.aclose()
