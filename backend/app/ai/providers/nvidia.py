"""NVIDIA NIM AI Provider.

A preset of ``OpenAICompatibleProvider`` for NVIDIA NIM (hosted at
https://integrate.api.nvidia.com/v1 or self-hosted). All request shaping,
tool calling, reasoning handling and error normalisation live in the generic
provider; this class only supplies NIM defaults.
"""

from __future__ import annotations

from typing import Any

from app.ai.capabilities import ModelCapabilities
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.structured import _clean_json_markdown  # noqa: F401  (re-exported for compatibility)

NVIDIA_HOSTED_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"


class NvidiaProvider(OpenAICompatibleProvider):
    """AIProvider implementation for NVIDIA NIM (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = NVIDIA_HOSTED_URL,
        api_key: str | None = None,
        model: str = NVIDIA_DEFAULT_MODEL,
        timeout_seconds: float = 45.0,
        *,
        capabilities: ModelCapabilities | None = None,
        capability_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        base_url = base_url or NVIDIA_HOSTED_URL
        super().__init__(
            name="nvidia",
            label="NVIDIA NIM",
            base_url=base_url,
            model=model or NVIDIA_DEFAULT_MODEL,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            # The hosted catalog needs a key; self-hosted NIM usually does not.
            require_api_key="integrate.api.nvidia.com" in base_url,
            capabilities=capabilities,
            capability_overrides=capability_overrides,
            **kwargs,
        )
