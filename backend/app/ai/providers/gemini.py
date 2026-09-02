"""Google Gemini AI Provider Implementation.

Connects to Google GenAI API using structured outputs while normalizing all
SDK errors into IRIS AIProviderError hierarchy.
"""

from __future__ import annotations

import asyncio
import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.provider import (
    AIConfigurationError,
    AIConnectionError,
    AIProvider,
    AIProviderError,
    AISchemaValidationError,
)
from app.ai.providers.omniroute import _clean_json_markdown
from app.core.logging import get_logger

logger = get_logger("iris.ai.providers.gemini")

T = TypeVar("T", bound=BaseModel)


class GeminiProvider(AIProvider):
    """AIProvider implementation for Google Gemini."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        timeout_seconds: float = 45.0,
    ):
        self._api_key = api_key or ""
        self._model = model or "gemini-2.5-flash"
        self._timeout = timeout_seconds
        self._client = None

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            if not self.enabled:
                raise AIConfigurationError(
                    "Gemini API key is not configured",
                    provider=self.name,
                )
            try:
                from google import genai

                self._client = genai.Client(api_key=self._api_key)
            except Exception as exc:
                raise AIConfigurationError(
                    f"Failed to initialize Google GenAI client: {exc}",
                    provider=self.name,
                    cause=exc,
                ) from exc
        return self._client

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
    ) -> T:
        if not self.enabled:
            raise AIConfigurationError(
                "Gemini provider is not enabled (missing GEMINI_API_KEY)",
                provider=self.name,
            )

        client = self._get_client()

        logger.info(
            "AI request started: provider=%s, model=%s",
            self.name,
            self._model,
        )

        def _call_gemini() -> str:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
            )
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
            return response.text or ""

        try:
            raw_text = await asyncio.wait_for(
                asyncio.to_thread(_call_gemini),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            logger.warning("AI request timeout: provider=%s, model=%s", self.name, self._model)
            raise AIConnectionError(
                f"Gemini request timed out after {self._timeout}s",
                provider=self.name,
                cause=exc,
            ) from exc
        except Exception as exc:
            logger.warning("AI Gemini SDK error: provider=%s, error=%s", self.name, exc)
            raise AIProviderError(
                f"Gemini API call failed: {exc}",
                provider=self.name,
                cause=exc,
            ) from exc

        if not raw_text:
            raise AISchemaValidationError(
                "Gemini returned empty response text",
                provider=self.name,
            )

        cleaned_text = _clean_json_markdown(raw_text)

        try:
            parsed_json = json.loads(cleaned_text)
            result = schema.model_validate(parsed_json)
        except json.JSONDecodeError as exc:
            logger.warning(
                "AI JSON decode failure: provider=%s, text=%s",
                self.name,
                cleaned_text[:200],
            )
            raise AISchemaValidationError(
                f"Gemini output was not valid JSON: {exc}",
                provider=self.name,
                cause=exc,
            ) from exc
        except ValidationError as exc:
            logger.warning(
                "AI schema validation failure: provider=%s, schema=%s, errors=%s",
                self.name,
                schema.__name__,
                exc.errors(),
            )
            raise AISchemaValidationError(
                f"Gemini output failed schema validation for {schema.__name__}: {exc}",
                provider=self.name,
                cause=exc,
            ) from exc

        logger.info(
            "AI request completed: provider=%s, model=%s, status=success",
            self.name,
            self._model,
        )
        return result
