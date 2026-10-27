"""Google Gemini AI Provider Implementation.

Connects to Google GenAI API using structured outputs while normalizing all
SDK errors into IRIS AIProviderError hierarchy.
"""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.capabilities import ModelCapabilities, resolve_capabilities
from app.ai.deadline import get_current_deadline
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
from app.ai.structured import _clean_json_markdown, extract_json
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.ai.providers.gemini")

T = TypeVar("T", bound=BaseModel)

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

active_turn_backend: ContextVar[OpenAICompatibleProvider | None] = ContextVar(
    "active_turn_backend", default=None
)


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
        is_live_key = bool(
            self._api_key and settings.gemini_api_key and self._api_key == settings.gemini_api_key
        )
        primary_kwargs = dict(chat_kwargs)
        if self._fallback_model and (primary_kwargs.get("max_retries") or 0) > 1:
            primary_kwargs["max_retries"] = 1
        if is_live_key and "gemma" not in chat_model.lower():
            primary_kwargs["extra_body"] = {
                "reasoning_effort": "none",
                **(primary_kwargs.get("extra_body") or {}),
            }
        per_attempt_timeout = min(timeout_seconds, 22.0) if self._fallback_model else timeout_seconds
        self._chat_backend = OpenAICompatibleProvider(
            name="gemini",
            label="Gemini",
            base_url=GEMINI_OPENAI_URL,
            model=chat_model,
            api_key=self._api_key,
            timeout_seconds=per_attempt_timeout,
            capabilities=self._caps,
            **primary_kwargs,
        )
        if self._fallback_model:
            fallback_chat_model = (
                f"models/{self._fallback_model}"
                if self._fallback_model.startswith("gemma-") and not self._fallback_model.startswith("models/")
                else self._fallback_model
            )
            fb_kwargs = dict(chat_kwargs)
            if (fb_kwargs.get("max_retries") or 0) > 1:
                fb_kwargs["max_retries"] = 1
            if is_live_key and "gemma" not in fallback_chat_model.lower():
                fb_kwargs["extra_body"] = {
                    "reasoning_effort": "none",
                    **(fb_kwargs.get("extra_body") or {}),
                }
            self._fallback_chat_backend = OpenAICompatibleProvider(
                name="gemini",
                label="Gemini",
                base_url=GEMINI_OPENAI_URL,
                model=fallback_chat_model,
                api_key=self._api_key,
                timeout_seconds=per_attempt_timeout,
                capabilities=resolve_capabilities(self._fallback_model),
                **fb_kwargs,
            )
        else:
            self._fallback_chat_backend = None

        self._secondary_fallbacks: list[OpenAICompatibleProvider] = []
        if is_live_key:
            if settings.groq_api_key:
                self._secondary_fallbacks.append(
                    OpenAICompatibleProvider(
                        name="groq",
                        label="Groq",
                        base_url=settings.groq_base_url or "https://api.groq.com/openai/v1",
                        model="qwen/qwen3.8-27b",
                        api_key=settings.groq_api_key,
                        timeout_seconds=min(timeout_seconds, 25.0),
                        capabilities=resolve_capabilities("qwen/qwen3.8-27b"),
                        max_retries=1,
                    )
                )
            seen_models = {
                self._model.replace("models/", ""),
                (self._fallback_model or "").replace("models/", ""),
            }
            for cand in ("gemini-3.5-flash", "gemini-3.1-flash-lite"):
                if cand not in seen_models:
                    seen_models.add(cand)
                    cand_model = cand
                    cand_extra = {"reasoning_effort": "none"}
                    self._secondary_fallbacks.append(
                        OpenAICompatibleProvider(
                            name="gemini",
                            label="Gemini",
                            base_url=GEMINI_OPENAI_URL,
                            model=cand_model,
                            api_key=self._api_key,
                            timeout_seconds=timeout_seconds,
                            capabilities=resolve_capabilities(cand),
                            max_retries=1,
                            extra_body=cand_extra,
                        )
                    )

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

        # Check turn-level stickiness: if a secondary backend already executed a tool call
        # in this turn, keep subsequent steps on that backend to prevent cross-provider signature rejections.
        sticky_backend = active_turn_backend.get()
        if sticky_backend is not None:
            try:
                return await sticky_backend.chat(
                    messages,
                    tools=tools,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except AIProviderError as exc:
                logger.warning(
                    "Sticky backend %s/%s failed in turn (%s); resetting stickiness and initiating failover",
                    sticky_backend.name,
                    sticky_backend.model,
                    exc,
                )
                active_turn_backend.set(None)

        try:
            res = await self._chat_backend.chat(
                messages,
                tools=tools,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            active_turn_backend.set(self._chat_backend)
            return res
        except AIProviderError as exc:
            last_err: AIProviderError = exc
            if self._fallback_chat_backend:
                logger.warning(
                    "Gemini primary model %s chat failed (%s); falling back to %s",
                    self._model,
                    exc,
                    self._fallback_model,
                )
                try:
                    res = await self._fallback_chat_backend.chat(
                        messages,
                        tools=tools,
                        response_format=response_format,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    active_turn_backend.set(self._fallback_chat_backend)
                    return res
                except AIProviderError as fb_exc:
                    last_err = fb_exc
            for sec_backend in self._secondary_fallbacks:
                try:
                    logger.warning(
                        "Gemini fallback chain trying secondary model %s/%s",
                        sec_backend.name,
                        sec_backend.model,
                    )
                    res = await sec_backend.chat(
                        messages,
                        tools=tools,
                        response_format=response_format,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    active_turn_backend.set(sec_backend)
                    return res
                except AIProviderError as sec_exc:
                    last_err = sec_exc
            raise last_err

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
                deadline = get_current_deadline()
                if deadline is not None:
                    per_call_timeout = max(1.0, deadline.per_attempt_timeout(self._timeout))
                else:
                    per_call_timeout = self._timeout
                raw_text = await asyncio.wait_for(
                    asyncio.to_thread(_call_gemini, model_to_use),
                    timeout=per_call_timeout,
                )
                if not raw_text:
                    raise AISchemaValidationError(
                        "Gemini returned empty response text",
                        provider=self.name,
                    )

                try:
                    parsed_json = extract_json(raw_text)
                except json.JSONDecodeError:
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
