"""Legacy compatibility shim for IRIS AI.

Delegates all calls directly to the active AIProvider from the provider factory.
This prevents legacy imports from breaking while keeping the system provider-agnostic.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.factory import get_ai_provider

T = TypeVar("T", bound=BaseModel)


class _AIProviderProxy:
    """Proxy object that forwards calls dynamically to the active AIProvider."""

    @property
    def _active_provider(self):
        return get_ai_provider()

    @property
    def name(self) -> str:
        return self._active_provider.name

    @property
    def model(self) -> str:
        return self._active_provider.model

    @property
    def enabled(self) -> bool:
        return self._active_provider.enabled

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
    ) -> T:
        return await self._active_provider.generate_structured(
            system=system,
            prompt=prompt,
            schema=schema,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._active_provider, name)


client = _AIProviderProxy()
