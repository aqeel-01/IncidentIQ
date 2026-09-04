"""Evaluation backends: local small, local 7B, and Groq."""

from __future__ import annotations

from typing import cast

from app.ai.errors import AIProviderConfigurationError
from app.ai.provider import AIProvider
from app.ai.providers.groq.provider import create_groq_provider
from app.ai.providers.ollama.provider import create_ollama_provider
from app.core.config import Settings
from app.domain.rca.eval.types import EvalBackendName

BACKEND_ORDER: tuple[EvalBackendName, ...] = (
    "local_small",
    "local_7b",
    "groq",
)


def build_eval_provider(backend: EvalBackendName, settings: Settings) -> AIProvider:
    """Construct the AI provider for a named evaluation backend."""

    if backend == "local_small":
        return create_ollama_provider(settings, model_size="small")
    if backend == "local_7b":
        return create_ollama_provider(settings, model_size="large")
    if backend == "groq":
        if not settings.groq_api_key.strip():
            msg = "GROQ_API_KEY is required for the groq evaluation backend"
            raise AIProviderConfigurationError(msg)
        if not settings.groq_model.strip():
            msg = "GROQ_MODEL is required for the groq evaluation backend"
            raise AIProviderConfigurationError(msg)
        return create_groq_provider(settings)

    msg = f"unknown evaluation backend: {backend}"
    raise ValueError(msg)


def parse_backends(raw: str | None) -> list[EvalBackendName]:
    """Parse a comma-separated backend list."""

    if raw is None or not raw.strip():
        return list(BACKEND_ORDER)

    backends: list[EvalBackendName] = []
    for part in raw.split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name not in BACKEND_ORDER:
            msg = (
                f"unknown backend '{name}'; expected one of {', '.join(BACKEND_ORDER)}"
            )
            raise ValueError(msg)
        backend = cast(EvalBackendName, name)
        if backend not in backends:
            backends.append(backend)
    if not backends:
        msg = "at least one evaluation backend is required"
        raise ValueError(msg)
    return backends
