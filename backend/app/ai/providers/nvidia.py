"""NVIDIA NIM AI Provider.

A preset of ``OpenAICompatibleProvider`` for NVIDIA NIM (hosted at
https://integrate.api.nvidia.com/v1 or self-hosted). All request shaping,
tool calling, reasoning handling and error normalisation live in the generic
provider; this class supplies NIM defaults without fallback.
"""

from __future__ import annotations

import os
from typing import Any

from app.ai.capabilities import ModelCapabilities
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
        timeout_seconds: float = 90.0,
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
