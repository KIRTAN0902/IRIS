"""Generic AI Provider abstraction and error hierarchy for IRIS.

Architecture:
IRIS Intelligence -> AIProvider (Interface) -> Provider Implementation -> Model -> Structured Schema

IRIS owns the intelligence; AI providers only provide model inference.

A provider exposes two levels of capability:

- ``generate_structured``: one prompt in, one validated Pydantic object out.
  Every provider supports this (it is the only method legacy/mock providers
  implement).
- ``chat``: multi-message conversation with optional native tool calling.
  Providers that implement it unlock the multi-step agent harness. The base
  class builds ``generate_structured`` on top of ``chat`` (schema prompting,
  JSON mode, reasoning stripping and a repair retry), so a new chat provider
  gets robust structured output for free.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.capabilities import ModelCapabilities, resolve_capabilities

T = TypeVar("T", bound=BaseModel)


# --- Standardized Error Hierarchy ---------------------------------------------


class AIProviderError(Exception):
    """Base exception for all AI provider-related failures.

    Provider-specific exceptions (httpx, google-genai, etc.) are caught and
    wrapped in this or a subclass to prevent provider leakage into business logic.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.cause = cause


class AIConfigurationError(AIProviderError):
    """Raised when an AI provider is missing required configuration (e.g. missing API key/URL)."""


class AIConnectionError(AIProviderError):
    """Raised when connection to the AI provider fails (e.g. network error, timeout)."""


class AISchemaValidationError(AIProviderError):
    """Raised when the AI output cannot be parsed into the expected Pydantic schema."""


class AICapabilityError(AIProviderError):
    """Raised when an AI provider is asked to perform a capability it does not support."""


# --- Provider-neutral chat primitives ------------------------------------------


@dataclass
class ToolDefinition:
    """A tool the model may call. ``parameters`` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass
class ToolCallRequest:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    # Set when the model produced arguments that are not a JSON object.
    argument_error: str | None = None


@dataclass
class ChatMessage:
    """One message in a provider-neutral conversation."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class ChatResult:
    """Normalised result of a chat completion."""

    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    reasoning: str | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


# --- AIProvider Interface -----------------------------------------------------


# Set for latency-sensitive turns (voice): providers apply the model's
# ``fast_body`` capability, e.g. skipping a reasoning model's thinking phase.
fast_turn: ContextVar[bool] = ContextVar("fast_turn", default=False)


class AIProvider(ABC):
    """Abstract base class for all AI providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier of the provider (e.g. 'nvidia', 'openai', 'gemini', 'mock')."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Active model name for this provider."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this provider is currently configured and operational."""

    @property
    def capabilities(self) -> ModelCapabilities:
        """Effective capabilities of the active model.

        Providers without ``chat`` cannot do native tool calling regardless of
        what the model profile says.
        """
        caps = resolve_capabilities(self.model)
        if not self.supports_chat:
            caps.native_tools = False
        return caps

    @property
    def supports_chat(self) -> bool:
        """True when this provider implements multi-message ``chat``."""
        return type(self).chat is not AIProvider.chat

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Run a chat completion, optionally offering tools to the model.

        Raises:
            AICapabilityError: If the provider does not implement chat.
            AIProviderError: On any transport/provider failure.
        """
        raise AICapabilityError(
            f"Provider '{self.name}' does not support multi-message chat", provider=self.name
        )

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
    ) -> T:
        """Generate a structured response adhering to the given Pydantic schema.

        The default implementation drives ``chat``: it requests the strongest
        JSON mode the model supports, strips reasoning/markdown wrappers, and
        gives the model ``structured_retries`` chances to repair invalid output.

        Args:
            system: System instructions / identity / rules.
            prompt: User prompt / context payload.
            schema: Pydantic model class to validate and return.

        Returns:
            Validated instance of the requested Pydantic schema `schema`.

        Raises:
            AIProviderError: On any failure (connection, timeout, malformed data, schema error).
        """
        from app.ai.structured import (
            compact_schema,
            parse_structured,
            repair_instruction,
            schema_instruction,
        )
        from app.core.config import settings

        if not self.enabled:
            raise AIConfigurationError(
                f"AI provider '{self.name}' is not configured", provider=self.name
            )

        caps = self.capabilities
        messages = [
            ChatMessage(role="system", content=f"{system}{schema_instruction(schema)}"),
            ChatMessage(role="user", content=prompt),
        ]

        last_error: AISchemaValidationError | None = None
        for _attempt in range(1 + max(0, settings.ai_structured_retries)):
            response_format: dict[str, Any] | None = None
            if caps.json_mode == "json_schema":
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": compact_schema(schema),
                        "strict": False,
                    },
                }
            elif caps.json_mode == "json_object":
                response_format = {"type": "json_object"}

            result = await self.chat(
                messages,
                response_format=response_format,
                temperature=caps.structured_temperature,
            )
            try:
                return parse_structured(result.content, schema, provider=self.name)
            except AISchemaValidationError as exc:
                last_error = exc
                messages.append(ChatMessage(role="assistant", content=result.content or ""))
                messages.append(ChatMessage(role="user", content=repair_instruction(exc)))
                # Capabilities may have been downgraded during the call.
                caps = self.capabilities

        assert last_error is not None
        from app.ai.health import ai_health

        ai_health.record_failure(self.name, self.model, last_error)
        raise last_error
