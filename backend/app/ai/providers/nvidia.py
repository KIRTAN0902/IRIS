"""NVIDIA NIM AI Provider.

A preset of ``OpenAICompatibleProvider`` for NVIDIA NIM (hosted at
https://integrate.api.nvidia.com/v1 or self-hosted). All request shaping,
tool calling, reasoning handling and error normalisation live in the generic
provider; this class supplies NIM defaults and resilient fallback.
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.ai.capabilities import ModelCapabilities
from app.ai.provider import (
    AIConfigurationError,
    AIConnectionError,
    AIProvider,
    AIProviderError,
    ChatMessage,
    ChatResult,
    ToolDefinition,
)
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.structured import _clean_json_markdown  # noqa: F401  (re-exported for compatibility)
from app.core.logging import get_logger

logger = get_logger("iris.ai.providers.nvidia")

NVIDIA_HOSTED_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "google/gemma-4-31b-it"


class NvidiaProvider(OpenAICompatibleProvider):
    """AIProvider implementation for NVIDIA NIM (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = NVIDIA_HOSTED_URL,
        api_key: str | None = None,
        model: str = NVIDIA_DEFAULT_MODEL,
        timeout_seconds: float = 40.0,
        *,
        capabilities: ModelCapabilities | None = None,
        capability_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        base_url = base_url or NVIDIA_HOSTED_URL
        resolved_key = api_key or os.environ.get("NVIDIA_API_KEY")
        super().__init__(
            name="nvidia",
            label="NVIDIA NIM",
            base_url=base_url,
            model=model or NVIDIA_DEFAULT_MODEL,
            api_key=resolved_key,
            timeout_seconds=timeout_seconds,
            require_api_key="integrate.api.nvidia.com" in base_url,
            capabilities=capabilities,
            capability_overrides=capability_overrides,
            **kwargs,
        )
        self._fallback_provider: AIProvider | None = None
        self._fallback_until: float = 0.0

    def _get_fallback(self) -> AIProvider | None:
        if self._fallback_provider is None:
            gemini_key = os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                from app.ai.providers.gemini import GeminiProvider
                self._fallback_provider = GeminiProvider(
                    api_key=gemini_key,
                    model="gemini-3.5-flash",
                    timeout_seconds=30.0,
                )
            else:
                groq_key = os.environ.get("GROQ_API_KEY")
                if groq_key:
                    self._fallback_provider = OpenAICompatibleProvider(
                        name="groq",
                        label="Groq Fallback",
                        base_url="https://api.groq.com/openai/v1",
                        model="qwen/qwen3.8-27b",
                        api_key=groq_key,
                        timeout_seconds=30.0,
                        require_api_key=True,
                    )
        return self._fallback_provider

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        now = time.time()
        if now < self._fallback_until:
            fallback = self._get_fallback()
            if fallback and fallback.enabled:
                return await fallback.chat(
                    messages,
                    tools=tools,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

        try:
            return await super().chat(
                messages,
                tools=tools,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except (AIConnectionError, AIProviderError) as exc:
            fallback = self._get_fallback()
            if fallback and fallback.enabled:
                self._fallback_until = time.time() + 180.0
                logger.warning(
                    "NVIDIA NIM (%s) request failed (%s); seamlessly falling back to %s (%s) for 3 minutes",
                    self._model,
                    exc,
                    fallback.name,
                    fallback.model,
                )
                return await fallback.chat(
                    messages,
                    tools=tools,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            raise
