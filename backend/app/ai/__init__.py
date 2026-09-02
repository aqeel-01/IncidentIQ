"""AI provider abstraction for IncidentIQ."""

from app.ai.errors import (
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderRegistrationError,
    AIProviderResponseError,
    AIProviderStructuredOutputError,
    AIProviderUnavailableError,
)
from app.ai.factory import (
    default_ai_provider_registry,
    register_default_providers,
    resolve_provider,
)
from app.ai.fallback import FallbackAIProvider
from app.ai.provider import AIProvider
from app.ai.providers.groq import (
    GroqProvider,
    create_groq_provider,
    groq_provider_config_from_settings,
)
from app.ai.providers.ollama import (
    OllamaProvider,
    create_ollama_provider,
    ollama_provider_config_from_settings,
)
from app.ai.registry import AIProviderRegistry
from app.ai.router import AIModelRouter, create_ai_model_router
from app.ai.routing import (
    is_fallback_enabled,
    resolve_rca_model_size,
    routing_plan_from_settings,
    select_fallback_provider_name,
    select_primary_provider_name,
)
from app.ai.types import (
    AIProviderHealthResult,
    AIProviderName,
    AIRoutingPlan,
    GenerateRequest,
    GenerateResponse,
    StructuredGenerateRequest,
    StructuredGenerateResponse,
)

__all__ = [
    "AIProvider",
    "AIProviderConfigurationError",
    "AIProviderError",
    "AIProviderHealthResult",
    "AIProviderName",
    "AIProviderRegistrationError",
    "AIProviderRegistry",
    "AIProviderResponseError",
    "AIProviderStructuredOutputError",
    "AIProviderUnavailableError",
    "AIModelRouter",
    "AIRoutingPlan",
    "FallbackAIProvider",
    "GenerateRequest",
    "GenerateResponse",
    "GroqProvider",
    "OllamaProvider",
    "StructuredGenerateRequest",
    "StructuredGenerateResponse",
    "create_ai_model_router",
    "create_groq_provider",
    "create_ollama_provider",
    "default_ai_provider_registry",
    "groq_provider_config_from_settings",
    "is_fallback_enabled",
    "ollama_provider_config_from_settings",
    "register_default_providers",
    "resolve_provider",
    "resolve_rca_model_size",
    "routing_plan_from_settings",
    "select_fallback_provider_name",
    "select_primary_provider_name",
]
