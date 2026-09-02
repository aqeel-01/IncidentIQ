"""AI provider interface and default structured generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

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

T = TypeVar("T", bound=BaseModel)


class AIProvider(ABC):
    """Abstract AI inference provider.

    Concrete vendor integrations (Ollama, Groq, etc.) implement this contract.
    Application code must depend on :class:`AIProvider`, not vendor SDKs.
    """

    @property
    @abstractmethod
    def name(self) -> AIProviderName:
        """Return the provider identifier."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the active model name for this provider instance."""

    @abstractmethod
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate unstructured text from a prompt."""

    async def structured_generate(
        self,
        request: StructuredGenerateRequest,
        *,
        response_model: type[T],
    ) -> StructuredGenerateResponse:
        """Generate JSON output and validate it against ``response_model``."""

        prompt = build_structured_prompt(
            request.prompt,
            response_model=response_model,
        )
        generation = await self.generate(
            GenerateRequest(
                prompt=prompt,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        )
        payload = extract_json_object(generation.content)
        validated = validate_structured_output(
            payload,
            response_model=response_model,
        )
        return StructuredGenerateResponse(
            data=validated,
            raw_content=generation.content,
            provider=generation.provider,
            model=generation.model,
            finish_reason=generation.finish_reason,
            usage=generation.usage,
        )

    @abstractmethod
    async def health_check(self) -> AIProviderHealthResult:
        """Check whether the provider is reachable and ready."""
