"""Model capability profiles.

IRIS treats every model as a black box with a set of *capabilities*. The
harness reads these to decide how to talk to the model (native tool calls vs.
prompted JSON, whether a JSON response mode can be requested, whether the model
emits reasoning traces, how much context it can hold, ...).

Resolution order (later wins):
1. ``DEFAULT_CAPABILITIES``
2. The first matching entry in ``MODEL_PROFILES`` (glob on the model id)
3. ``AI_CAPABILITIES`` JSON from the environment

Profiles are only a starting point: ``OpenAICompatibleProvider`` downgrades a
capability at runtime when the endpoint rejects it, so an unknown model works
without any code change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from fnmatch import fnmatch
from typing import Any, Literal

JsonMode = Literal["json_schema", "json_object", "none"]
MaxTokensParam = Literal["max_tokens", "max_completion_tokens"]


@dataclass
class ModelCapabilities:
    """What a model/endpoint supports and how IRIS should drive it."""

    # Native OpenAI-style function/tool calling.
    native_tools: bool = True
    # Strongest response_format the endpoint accepts for structured output.
    json_mode: JsonMode = "json_object"
    # Model emits reasoning (<think> blocks or a reasoning_content field).
    reasoning: bool = False
    # Endpoint accepts a "system" role message (otherwise merged into user).
    system_role: bool = True
    # Endpoint accepts a temperature parameter.
    supports_temperature: bool = True
    # Name of the output-length parameter.
    max_tokens_param: MaxTokensParam = "max_tokens"
    # Approximate context window in tokens; drives history/tool-result budgets.
    context_window: int = 32_768
    # Output tokens to request per call.
    max_output_tokens: int = 4_096
    # Sampling temperature for conversational/agent turns.
    temperature: float = 0.3
    # Sampling temperature for schema-constrained extraction.
    structured_temperature: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def merged(self, overrides: dict[str, Any] | None) -> ModelCapabilities:
        if not overrides:
            return replace(self)
        known = {f.name for f in fields(self)}
        return replace(self, **{k: v for k, v in overrides.items() if k in known})

    # --- Budgets derived from the context window --------------------------

    @property
    def history_messages(self) -> int:
        """How many prior conversation messages to replay each turn."""
        if self.context_window <= 16_384:
            return 6
        if self.context_window <= 65_536:
            return 12
        return 20

    @property
    def tool_result_chars(self) -> int:
        """Max characters of a single tool result fed back to the model."""
        if self.context_window <= 16_384:
            return 2_000
        if self.context_window <= 65_536:
            return 6_000
        return 12_000


DEFAULT_CAPABILITIES = ModelCapabilities()

# Ordered (first match wins). Patterns match the full model id and the part
# after the last "/", case-insensitively. Keep entries to facts that matter for
# how the harness drives the model; everything else is learned at runtime.
MODEL_PROFILES: list[tuple[str, dict[str, Any]]] = [
    # Reasoning models: let them think, then extract JSON (guided JSON decoding
    # from the first token suppresses the reasoning phase).
    (
        "*nemotron*",
        {
            "reasoning": True,
            "json_mode": "none",
            "context_window": 131_072,
            "max_output_tokens": 8_192,
        },
    ),
    (
        "*deepseek-r1*",
        {
            "reasoning": True,
            "native_tools": False,
            "json_mode": "none",
            "context_window": 65_536,
            "max_output_tokens": 8_192,
        },
    ),
    (
        "*deepseek-reasoner*",
        {
            "reasoning": True,
            "native_tools": False,
            "json_mode": "none",
            "context_window": 65_536,
            "max_output_tokens": 8_192,
        },
    ),
    (
        "*qwq*",
        {
            "reasoning": True,
            "json_mode": "none",
            "context_window": 32_768,
            "max_output_tokens": 8_192,
        },
    ),
    (
        "*qwen3*",
        {
            "reasoning": True,
            "json_mode": "none",
            "context_window": 131_072,
            "max_output_tokens": 8_192,
        },
    ),
    (
        "o1*",
        {
            "reasoning": True,
            "supports_temperature": False,
            "max_tokens_param": "max_completion_tokens",
            "json_mode": "json_schema",
            "context_window": 200_000,
            "max_output_tokens": 16_384,
        },
    ),
    (
        "o3*",
        {
            "reasoning": True,
            "supports_temperature": False,
            "max_tokens_param": "max_completion_tokens",
            "json_mode": "json_schema",
            "context_window": 200_000,
            "max_output_tokens": 16_384,
        },
    ),
    (
        "o4*",
        {
            "reasoning": True,
            "supports_temperature": False,
            "max_tokens_param": "max_completion_tokens",
            "json_mode": "json_schema",
            "context_window": 200_000,
            "max_output_tokens": 16_384,
        },
    ),
    (
        "gpt-5*",
        {
            "reasoning": True,
            "supports_temperature": False,
            "max_tokens_param": "max_completion_tokens",
            "json_mode": "json_schema",
            "context_window": 400_000,
            "max_output_tokens": 16_384,
        },
    ),
    # Non-reasoning frontier/open models.
    ("gpt-4o*", {"json_mode": "json_schema", "context_window": 128_000}),
    ("gpt-4.1*", {"json_mode": "json_schema", "context_window": 1_000_000}),
    ("claude*", {"json_mode": "none", "context_window": 200_000, "max_output_tokens": 8_192}),
    ("gemini*", {"context_window": 1_000_000, "max_output_tokens": 8_192}),
    ("*llama-3*", {"context_window": 131_072}),
    ("*llama-4*", {"context_window": 1_000_000}),
    ("*mistral*", {"context_window": 32_768}),
    ("*mixtral*", {"context_window": 32_768}),
    ("mock*", {"native_tools": False, "json_mode": "none"}),
]


def profile_for_model(model: str) -> dict[str, Any]:
    """Return the profile overrides for ``model`` (empty dict if none match)."""
    model_l = (model or "").lower()
    short = model_l.rsplit("/", 1)[-1]
    for pattern, profile in MODEL_PROFILES:
        if fnmatch(model_l, pattern) or fnmatch(short, pattern):
            return profile
    return {}


def resolve_capabilities(model: str, overrides: dict[str, Any] | None = None) -> ModelCapabilities:
    """Resolve the effective capabilities for a model id."""
    return DEFAULT_CAPABILITIES.merged(profile_for_model(model)).merged(overrides)
