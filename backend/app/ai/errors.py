"""AI provider-specific errors."""

from __future__ import annotations


class AIProviderError(Exception):
    """Base error for AI provider operations."""


class AIProviderRegistrationError(AIProviderError):
    """Raised when a provider is unknown or already registered."""


class AIProviderUnavailableError(AIProviderError):
    """Raised when a provider fails a health check or cannot be reached."""


class AIProviderResponseError(AIProviderError):
    """Raised when a provider returns an invalid or empty response."""


class AIProviderStructuredOutputError(AIProviderError):
    """Raised when structured output cannot be parsed or validated."""


class AIProviderConfigurationError(AIProviderError):
    """Raised when provider configuration is incomplete or invalid."""
