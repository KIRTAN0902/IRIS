"""Generic AI Provider abstraction and error hierarchy for IRIS.

Architecture:
IRIS Intelligence -> AIProvider (Interface) -> Provider Implementation -> Model -> Structured Schema

IRIS owns the intelligence; AI providers only provide model inference.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

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


# --- AIProvider Interface -----------------------------------------------------


class AIProvider(ABC):
    """Abstract base class for all AI providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier of the provider (e.g. 'omniroute', 'gemini', 'mock')."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Active model name for this provider."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this provider is currently configured and operational."""

    @abstractmethod
    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
    ) -> T:
        """Generate a structured response adhering to the given Pydantic schema.

        Args:
            system: System instructions / identity / rules.
            prompt: User prompt / context payload.
            schema: Pydantic model class to validate and return.

        Returns:
            Validated instance of the requested Pydantic schema `schema`.

        Raises:
            AIProviderError: On any failure (connection, timeout, malformed data, schema error).
        """
