"""Mock AI Provider Implementation for Testing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.provider import AIProvider

T = TypeVar("T", bound=BaseModel)


class MockProvider(AIProvider):
    """Mock AI Provider for testing and offline verification."""

    def __init__(
        self,
        name: str = "mock",
        model: str = "mock-model-v1",
        default_response_generator: Callable[..., Any] | None = None,
    ):
        self._name = name
        self._model = model
        self._generator = default_response_generator
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
    def call_history(self) -> list[dict[str, Any]]:
        return self._call_history

    def set_generator(self, generator: Callable[..., Any]) -> None:
        self._generator = generator

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
