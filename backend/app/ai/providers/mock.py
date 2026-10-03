"""Mock AI Provider Implementation for Testing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.capabilities import ModelCapabilities, resolve_capabilities
from app.ai.provider import AIProvider, ChatMessage, ChatResult, ToolDefinition

T = TypeVar("T", bound=BaseModel)


class MockProvider(AIProvider):
    """Mock AI Provider for testing and offline verification.

    By default it only implements ``generate_structured`` (the agent then uses
    the prompted-JSON strategy). Pass ``chat_generator`` to also script
    ``chat`` responses and exercise the native tool-calling loop.
    """

    def __init__(
        self,
        name: str = "mock",
        model: str = "mock-model-v1",
        default_response_generator: Callable[..., Any] | None = None,
        chat_generator: Callable[..., ChatResult] | None = None,
        capabilities: ModelCapabilities | None = None,
    ):
        self._name = name
        self._model = model
        self._generator = default_response_generator
        self._chat_generator = chat_generator
        self._caps = capabilities
        self._call_history: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def enabled(self) -> bool:
        return True

    @property
    def supports_chat(self) -> bool:
        return self._chat_generator is not None

    @property
    def capabilities(self) -> ModelCapabilities:
        caps = self._caps or resolve_capabilities(self._model)
        if self._caps is None:
            caps.native_tools = self.supports_chat
        return caps

    @property
    def call_history(self) -> list[dict[str, Any]]:
        return self._call_history

    def set_generator(self, generator: Callable[..., Any]) -> None:
        self._generator = generator

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        if self._chat_generator is None:
            return await super().chat(messages, tools=tools)
        self._call_history.append({"messages": list(messages), "tools": tools})
        return self._chat_generator(messages=messages, tools=tools)

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
    ) -> T:
        self._call_history.append({"system": system, "prompt": prompt, "schema": schema})
        if self._generator is not None:
            res = self._generator(system=system, prompt=prompt, schema=schema)
            if isinstance(res, schema):
                return res
            if isinstance(res, dict):
                return schema.model_validate(res)
            return res
        # Default empty model instantiation if fields allow it
        return schema.model_validate({})
