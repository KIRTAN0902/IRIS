"""AI Provider Factory.

Instantiates and configures AIProvider instances based on application configuration.
All provider-specific selection logic is isolated here.
"""

from __future__ import annotations

from app.ai.provider import AIConfigurationError, AIProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.mock import MockProvider
from app.ai.providers.omniroute import OmniRouteProvider
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.ai.factory")

_CURRENT_PROVIDER: AIProvider | None = None


def create_ai_provider(provider_name: str | None = None) -> AIProvider:
    """Create a new AIProvider instance based on the specified or configured provider."""
    name = (provider_name or settings.ai_provider).strip().lower()

    if name == "omniroute":
        return OmniRouteProvider(
            base_url=settings.omniroute_base_url,
            api_key=settings.omniroute_api_key,
            model=settings.omniroute_model,
            timeout_seconds=settings.omniroute_timeout_seconds,
        )
    elif name == "gemini":
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
        )
    elif name == "mock":
        return MockProvider(
            name="mock",
            model="mock-model",
        )
    else:
        raise AIConfigurationError(
            f"Unsupported AI provider '{name}'. Supported providers: 'omniroute', 'gemini', 'mock'."
        )


def get_ai_provider(provider_name: str | None = None) -> AIProvider:
    """Retrieve the active AI provider singleton.

    If a specific provider name is requested or no singleton exists, initializes one.
    """
    global _CURRENT_PROVIDER
    if provider_name is not None:
        return create_ai_provider(provider_name)
    if _CURRENT_PROVIDER is None:
        _CURRENT_PROVIDER = create_ai_provider()
    return _CURRENT_PROVIDER


def set_ai_provider(provider: AIProvider | None) -> None:
    """Explicitly override the active AI provider (useful for testing)."""
    global _CURRENT_PROVIDER
    _CURRENT_PROVIDER = provider


def reset_ai_provider() -> None:
    """Reset the cached AI provider instance so it will be re-created on next access."""
    global _CURRENT_PROVIDER
    _CURRENT_PROVIDER = None
