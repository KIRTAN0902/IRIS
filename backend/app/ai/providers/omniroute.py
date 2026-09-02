"""OmniRoute AI Provider Implementation.

Connects to OmniRoute (or any OpenAI-compatible API gateway) to provide structured
Pydantic model responses while normalizing all HTTP, timeout, and parsing errors.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.provider import (
    AIConfigurationError,
    AIConnectionError,
    AIProvider,
    AIProviderError,
    AISchemaValidationError,
)
from app.core.logging import get_logger

logger = get_logger("iris.ai.providers.omniroute")

T = TypeVar("T", bound=BaseModel)


def _clean_json_markdown(text: str) -> str:
    """Strip markdown code fences (e.g. ```json ... ```) and leading/trailing whitespace."""
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


class OmniRouteProvider(AIProvider):
    """AIProvider implementation for OmniRoute (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:20128/v1",
        api_key: str | None = None,
        model: str = "auto/best-fast",
        timeout_seconds: float = 45.0,
    ):
        self._base_url = (base_url or "http://localhost:20128/v1").rstrip("/")
        self._api_key = api_key or ""
        self._model = model or "auto/best-fast"
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "omniroute"

    @property
    def model(self) -> str:
        return self._model

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
    ) -> T:
        if not self.enabled:
            raise AIConfigurationError(
                "OmniRoute provider is not configured (missing base URL)",
                provider=self.name,
            )

        endpoint = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Request schema-directed output
        json_instructions = (
            f"\n\nCRITICAL: Respond ONLY with a valid JSON object strictly matching "
            f"this JSON schema:\n{json.dumps(schema.model_json_schema())}"
        )
        full_system = f"{system}{json_instructions}"

        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "stream": False,
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "AI request started: provider=%s, model=%s, endpoint=%s",
            self.name,
            self._model,
            endpoint,
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http_client:
                response = await http_client.post(endpoint, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("AI request timeout: provider=%s, model=%s", self.name, self._model)
            raise AIConnectionError(
                f"OmniRoute request timed out after {self._timeout}s",
                provider=self.name,
                cause=exc,
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            logger.warning(
                "AI connection error: provider=%s, endpoint=%s, error=%s",
                self.name,
                endpoint,
                exc,
            )
            raise AIConnectionError(
                f"Failed to connect to OmniRoute at {self._base_url}: {exc}",
                provider=self.name,
                cause=exc,
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "AI HTTP status error: provider=%s, status_code=%s",
                self.name,
                exc.response.status_code,
            )
            raise AIProviderError(
                f"OmniRoute HTTP error {exc.response.status_code}: {exc.response.text[:300]}",
                provider=self.name,
                cause=exc,
            ) from exc
        except Exception as exc:
            logger.warning("AI request unexpected error: provider=%s, error=%s", self.name, exc)
            raise AIProviderError(
                f"OmniRoute request failed unexpectedly: {exc}",
                provider=self.name,
                cause=exc,
            ) from exc

        # Extract content from OpenAI-compatible choices array
        try:
            choices = data.get("choices", [])
            if not choices:
                raise AISchemaValidationError(
                    "OmniRoute returned no choices in completion response",
                    provider=self.name,
                )
            raw_content = choices[0].get("message", {}).get("content", "")
            if not raw_content:
                raise AISchemaValidationError(
                    "OmniRoute returned empty message content",
                    provider=self.name,
                )
        except Exception as exc:
            if isinstance(exc, AIProviderError):
                raise
            raise AISchemaValidationError(
                f"Malformed completion format from OmniRoute: {exc}",
                provider=self.name,
                cause=exc,
            ) from exc

        # Clean markdown wrappers if returned
        cleaned_content = _clean_json_markdown(raw_content)

        # Validate with Pydantic schema
        try:
            parsed_json = json.loads(cleaned_content)
            result = schema.model_validate(parsed_json)
        except json.JSONDecodeError as exc:
            logger.warning(
                "AI JSON decode failure: provider=%s, raw_content=%s",
                self.name,
                cleaned_content[:200],
            )
            raise AISchemaValidationError(
                f"OmniRoute output was not valid JSON: {exc}",
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
                f"OmniRoute output failed schema validation for {schema.__name__}: {exc}",
                provider=self.name,
                cause=exc,
            ) from exc

        logger.info(
            "AI request completed: provider=%s, model=%s, status=success",
            self.name,
            self._model,
        )
        return result
