"""AI Provider Factory.

Instantiates and configures AIProvider instances based on application configuration.
All provider-specific selection logic is isolated here.

Every backend except Gemini's native SDK and the mock is the same
``OpenAICompatibleProvider``; a *preset* only supplies a default base URL and
whether an API key is required. Values resolve in this order:

    AI_* setting  ->  legacy vendor setting (NVIDIA_*, GEMINI_*)  ->  preset default

So moving from Nemotron to any other model is a configuration change:

    AI_PROVIDER=openrouter
    AI_MODEL=anthropic/claude-sonnet-4.5
    AI_API_KEY=...
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.ai.provider import AIConfigurationError, AIProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.mock import MockProvider
from app.ai.providers.nvidia import NVIDIA_DEFAULT_MODEL, NVIDIA_HOSTED_URL, NvidiaProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.ai.factory")

_CURRENT_PROVIDER: AIProvider | None = None


@dataclass(frozen=True)
class ProviderPreset:
    label: str
    base_url: str | None
    requires_api_key: bool = True
    # Conventional env var for this vendor's key, read as a last resort.
    api_key_env: str | None = None


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "nvidia": ProviderPreset("NVIDIA NIM", NVIDIA_HOSTED_URL, api_key_env="NVIDIA_API_KEY"),
    "openai": ProviderPreset("OpenAI", "https://api.openai.com/v1", api_key_env="OPENAI_API_KEY"),
    "openrouter": ProviderPreset(
        "OpenRouter", "https://openrouter.ai/api/v1", api_key_env="OPENROUTER_API_KEY"
    ),
    "groq": ProviderPreset("Groq", "https://api.groq.com/openai/v1", api_key_env="GROQ_API_KEY"),
    "together": ProviderPreset(
        "Together AI", "https://api.together.xyz/v1", api_key_env="TOGETHER_API_KEY"
    ),
    "deepseek": ProviderPreset(
        "DeepSeek", "https://api.deepseek.com/v1", api_key_env="DEEPSEEK_API_KEY"
    ),
    "mistral": ProviderPreset(
        "Mistral", "https://api.mistral.ai/v1", api_key_env="MISTRAL_API_KEY"
    ),
    "fireworks": ProviderPreset(
        "Fireworks", "https://api.fireworks.ai/inference/v1", api_key_env="FIREWORKS_API_KEY"
    ),
    "anthropic": ProviderPreset(
        "Anthropic", "https://api.anthropic.com/v1", api_key_env="ANTHROPIC_API_KEY"
    ),
    "ollama": ProviderPreset("Ollama", "http://localhost:11434/v1", requires_api_key=False),
    "lmstudio": ProviderPreset("LM Studio", "http://localhost:1234/v1", requires_api_key=False),
    "vllm": ProviderPreset("vLLM", None, requires_api_key=False),
    "openai_compatible": ProviderPreset("OpenAI-compatible", None, requires_api_key=False),
}

SUPPORTED_PROVIDERS = sorted([*PROVIDER_PRESETS, "gemini", "mock"])


def _first(*values: object) -> str | None:
    for v in values:
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _common_kwargs() -> dict:
    return {
        "capability_overrides": settings.json_setting("ai_capabilities"),
        "temperature": settings.ai_temperature,
        "max_tokens": settings.ai_max_tokens,
        "max_retries": settings.ai_max_retries,
        "extra_body": settings.json_setting("ai_extra_body"),
        "extra_headers": settings.json_setting("ai_extra_headers"),
    }


def create_ai_provider(provider_name: str | None = None) -> AIProvider:
    """Create a new AIProvider instance based on the specified or configured provider."""
    name = (provider_name or settings.ai_provider).strip().lower().replace("-", "_")

    if name == "mock":
        return MockProvider(name="mock", model=_first(settings.ai_model) or "mock-model")

    if name == "gemini":
        return GeminiProvider(
            api_key=_first(settings.ai_api_key, settings.gemini_api_key),
            model=_first(settings.ai_model, settings.gemini_model) or "gemini-2.5-flash",
            timeout_seconds=settings.ai_timeout_seconds or settings.gemini_timeout_seconds,
            **_common_kwargs(),
        )

    preset = PROVIDER_PRESETS.get(name)
    if preset is None:
        raise AIConfigurationError(
            f"Unsupported AI provider '{name}'. Supported providers: "
            + ", ".join(f"'{p}'" for p in SUPPORTED_PROVIDERS)
            + ". Any OpenAI-compatible endpoint works via AI_PROVIDER=openai_compatible + AI_BASE_URL."
        )

    if name == "nvidia":
        return NvidiaProvider(
            base_url=_first(settings.ai_base_url, settings.nvidia_base_url) or NVIDIA_HOSTED_URL,
            api_key=_first(settings.ai_api_key, settings.nvidia_api_key),
            model=_first(settings.ai_model, settings.nvidia_model) or NVIDIA_DEFAULT_MODEL,
            timeout_seconds=settings.ai_timeout_seconds or settings.nvidia_timeout_seconds,
            **_common_kwargs(),
        )

    api_key = _first(
        settings.ai_api_key,
        os.environ.get(preset.api_key_env) if preset.api_key_env else None,
    )
    return OpenAICompatibleProvider(
        name=name,
        label=preset.label,
        base_url=_first(settings.ai_base_url, preset.base_url) or "",
        model=_first(settings.ai_model) or "",
        api_key=api_key,
        timeout_seconds=settings.ai_timeout_seconds or 60.0,
        require_api_key=preset.requires_api_key,
        **_common_kwargs(),
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
        logger.info(
            "AI provider initialised: provider=%s model=%s enabled=%s capabilities=%s",
            _CURRENT_PROVIDER.name,
            _CURRENT_PROVIDER.model,
            _CURRENT_PROVIDER.enabled,
            _CURRENT_PROVIDER.capabilities.to_dict(),
        )
    return _CURRENT_PROVIDER


def set_ai_provider(provider: AIProvider | None) -> None:
    """Explicitly override the active AI provider (useful for testing)."""
    global _CURRENT_PROVIDER
    _CURRENT_PROVIDER = provider


def reset_ai_provider() -> None:
    """Reset the cached AI provider instance so it will be re-created on next access."""
    global _CURRENT_PROVIDER
    _CURRENT_PROVIDER = None
