"""Google Gemini AI Provider Implementation.

Connects to Google GenAI API using structured outputs while normalizing all
SDK errors into IRIS AIProviderError hierarchy.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.capabilities import ModelCapabilities, resolve_capabilities
from app.ai.provider import (
    AIConfigurationError,
    AIConnectionError,
    AIProvider,
    AIProviderError,
    AISchemaValidationError,
    ChatMessage,
    ChatResult,
    ToolDefinition,
)
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.structured import _clean_json_markdown
from app.core.logging import get_logger

logger = get_logger("iris.ai.providers.gemini")

T = TypeVar("T", bound=BaseModel)

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class GeminiProvider(AIProvider):
    """AIProvider implementation for Google Gemini.

    Structured output uses the native SDK (server-side schema enforcement);
    multi-turn chat and tool calling go through Gemini's OpenAI-compatible
    endpoint so the agent harness can drive Gemini like any other model.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        fallback_model: str | None = None,
        timeout_seconds: float = 45.0,
        *,
        capability_overrides: dict[str, Any] | None = None,
        **chat_kwargs: Any,
    ):
        self._api_key = api_key or ""
        self._model = model or "gemini-2.5-flash"
        self._fallback_model = fallback_model if (fallback_model and fallback_model != self._model) else None
        self._timeout = timeout_seconds
        self._client = None
        self._caps: ModelCapabilities = resolve_capabilities(self._model, capability_overrides)
        chat_model = (
            f"models/{self._model}"
            if self._model.startswith("gemma-") and not self._model.startswith("models/")
            else self._model
        )
        self._chat_backend = OpenAICompatibleProvider(
            name="gemini",
            label="Gemini",
            base_url=GEMINI_OPENAI_URL,
            model=chat_model,
            api_key=self._api_key,
            timeout_seconds=timeout_seconds,
            capabilities=self._caps,
            **chat_kwargs,
        )
        if self._fallback_model:
            fallback_chat_model = (
                f"models/{self._fallback_model}"
                if self._fallback_model.startswith("gemma-") and not self._fallback_model.startswith("models/")
                else self._fallback_model
            )
            self._fallback_chat_backend = OpenAICompatibleProvider(
                name="gemini",
                label="Gemini",
                base_url=GEMINI_OPENAI_URL,
                model=fallback_chat_model,
                api_key=self._api_key,
                timeout_seconds=timeout_seconds,
                capabilities=resolve_capabilities(self._fallback_model),
                **chat_kwargs,
            )
        else:
            self._fallback_chat_backend = None

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    @property
    def fallback_model(self) -> str | None:
        return self._fallback_model

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._caps

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        if not self.enabled:
            raise AIConfigurationError(
                "Gemini provider is not enabled (missing API key)",
                provider=self.name,
            )
        try:
            return await self._chat_backend.chat(
                messages,
                tools=tools,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except AIProviderError as exc:
            if self._fallback_chat_backend:
                logger.warning(
                    "Gemini primary model %s chat failed (%s); falling back to %s",
                    self._model,
                    exc,
                    self._fallback_model,
                )
                return await self._fallback_chat_backend.chat(
                    messages,
                    tools=tools,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            raise

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

        def _strip_additional_properties(schema_obj: Any) -> Any:
            if isinstance(schema_obj, dict):
                return {
                    k: _strip_additional_properties(v)
                    for k, v in schema_obj.items()
                    if k != "additionalProperties"
                }
            if isinstance(schema_obj, list):
                return [_strip_additional_properties(item) for item in schema_obj]
            return schema_obj

        clean_response_schema = (
            _strip_additional_properties(schema.model_json_schema())
            if hasattr(schema, "model_json_schema")
            else schema
        )

        def _call_gemini(model_to_use: str) -> str:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system,
                temperature=self._caps.structured_temperature,
                response_mime_type="application/json",
                response_schema=clean_response_schema,
            )
            normalized_model = (
                f"models/{model_to_use}"
                if model_to_use.startswith("gemma-") and not model_to_use.startswith("models/")
                else model_to_use
            )
            response = client.models.generate_content(
                model=normalized_model,
                contents=prompt,
                config=config,
            )
            return response.text or ""

        models_to_try = [self._model]
        if self._fallback_model:
            models_to_try.append(self._fallback_model)

        last_exc: Exception | None = None
        for idx, model_to_use in enumerate(models_to_try):
            logger.info(
                "AI request started: provider=%s, model=%s",
                self.name,
                model_to_use,
            )
            try:
                raw_text = await asyncio.wait_for(
                    asyncio.to_thread(_call_gemini, model_to_use),
                    timeout=self._timeout,
                )
                if not raw_text:
                    raise AISchemaValidationError(
                        "Gemini returned empty response text",
                        provider=self.name,
                    )

                cleaned_text = _clean_json_markdown(raw_text)
                parsed_json = json.loads(cleaned_text)
                result = schema.model_validate(parsed_json)

                if idx > 0:
                    logger.info(
                        "AI request completed using fallback model: provider=%s, model=%s",
                        self.name,
                        model_to_use,
                    )
                else:
                    logger.info(
                        "AI request completed: provider=%s, model=%s, status=success",
                        self.name,
                        self._model,
                    )
                return result
            except Exception as exc:
                last_exc = exc
                if idx < len(models_to_try) - 1:
                    logger.warning(
                        "Gemini primary model %s failed (%s); trying fallback model %s",
                        model_to_use,
                        exc,
                        models_to_try[idx + 1],
                    )
                    continue

        # If native SDK calls fail (e.g. 503 UNAVAILABLE or schema incompatibility),
        # fall back to prompt-driven chat JSON generation.
        try:
            logger.info("Falling back to chat backend for structured generation: provider=%s", self.name)
            return await super().generate_structured(
                system=system,
                prompt=prompt,
                schema=schema,
            )
        except Exception as fallback_exc:
            logger.warning("Chat backend structured fallback also failed: %s", fallback_exc)

        if isinstance(last_exc, TimeoutError):
            logger.warning("AI request timeout: provider=%s, model=%s", self.name, self._model)
            raise AIConnectionError(
                f"Gemini request timed out after {self._timeout}s",
                provider=self.name,
                cause=last_exc,
            ) from last_exc
        if isinstance(last_exc, (json.JSONDecodeError, ValidationError)):
            raise AISchemaValidationError(
                f"Gemini output failed schema validation: {last_exc}",
                provider=self.name,
                cause=last_exc,
            ) from last_exc
        if isinstance(last_exc, AIProviderError):
            raise last_exc
        logger.warning("AI Gemini SDK error: provider=%s, error=%s", self.name, last_exc)
        raise AIProviderError(
            f"Gemini API call failed: {last_exc}",
            provider=self.name,
            cause=last_exc,
        ) from last_exc
