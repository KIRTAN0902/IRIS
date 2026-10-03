"""Generic OpenAI-compatible Chat Completions provider.

One implementation serves every endpoint that speaks the ``/chat/completions``
protocol: NVIDIA NIM, OpenAI, OpenRouter, Groq, Together, DeepSeek, Mistral,
Fireworks, Anthropic's compatibility endpoint, Gemini's compatibility endpoint,
Ollama, LM Studio, vLLM, llama.cpp, ...

Model differences are handled through ``ModelCapabilities`` rather than code:
the request is shaped from capabilities, and when an endpoint rejects a
parameter (tools, response_format, temperature, system role, max_tokens) the
capability is downgraded and the request retried, so the next call goes out
right first time.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.ai.capabilities import ModelCapabilities, resolve_capabilities
from app.ai.provider import (
    AIConfigurationError,
    AIConnectionError,
    AIProvider,
    AIProviderError,
    AISchemaValidationError,
    ChatMessage,
    ChatResult,
    ToolCallRequest,
    ToolDefinition,
)
from app.ai.structured import split_reasoning
from app.core.logging import get_logger

logger = get_logger("iris.ai.providers.openai_compatible")

_RETRYABLE_STATUS = {408, 409, 429, 502, 503, 504}
_MAX_ADAPTATIONS = 4


class OpenAICompatibleProvider(AIProvider):
    """AIProvider for any OpenAI-compatible Chat Completions endpoint."""

    def __init__(
        self,
        *,
        name: str = "openai_compatible",
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        require_api_key: bool = True,
        capabilities: ModelCapabilities | None = None,
        capability_overrides: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 2,
        extra_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        label: str | None = None,
    ):
        self._name = name
        self._label = label or name
        self._base_url = (base_url or "").rstrip("/")
        self._model = model or ""
        self._api_key = api_key or ""
        self._timeout = timeout_seconds
        self._require_api_key = require_api_key
        self._caps = capabilities or resolve_capabilities(self._model, capability_overrides)
        if temperature is not None:
            self._caps.temperature = temperature
        if max_tokens is not None:
            self._caps.max_output_tokens = max_tokens
        self._max_retries = max(0, max_retries)
        self._extra_body = extra_body or {}
        self._extra_headers = extra_headers or {}

    # --- Identity & configuration ---------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def enabled(self) -> bool:
        if not self._base_url or not self._model:
            return False
        if self._require_api_key and not self._api_key:
            return False
        return True

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._caps

    def _missing_config(self) -> str:
        missing = []
        if not self._base_url:
            missing.append("base URL (AI_BASE_URL)")
        if not self._model:
            missing.append("model (AI_MODEL)")
        if self._require_api_key and not self._api_key:
            missing.append("API key (AI_API_KEY)")
        return ", ".join(missing)

    # --- Request shaping -------------------------------------------------------

    def _serialize_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        pending_system: list[str] = []
        for m in messages:
            if m.role == "system" and not self._caps.system_role:
                pending_system.append(m.content or "")
                continue
            msg: dict[str, Any] = {"role": m.role}
            content = m.content
            if pending_system and m.role == "user":
                content = "\n\n".join([*pending_system, content or ""])
                pending_system = []
            if m.role == "assistant" and m.tool_calls:
                msg["content"] = content or ""
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in m.tool_calls
                ]
            else:
                msg["content"] = content or ""
            if m.role == "tool":
                msg["tool_call_id"] = m.tool_call_id
            out.append(msg)
        if pending_system:
            out.insert(0, {"role": "user", "content": "\n\n".join(pending_system)})
        return out

    def _build_body(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None,
        response_format: dict[str, Any] | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        caps = self._caps
        body: dict[str, Any] = {
            "model": self._model,
            "messages": self._serialize_messages(messages),
            "stream": False,
        }
        body[caps.max_tokens_param] = max_tokens or caps.max_output_tokens
        if caps.supports_temperature:
            body["temperature"] = caps.temperature if temperature is None else temperature
        if tools and caps.native_tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"
        if response_format and not body.get("tools"):
            rf_type = response_format.get("type")
            if rf_type == "json_schema" and caps.json_mode == "json_schema":
                body["response_format"] = response_format
            elif rf_type in {"json_schema", "json_object"} and caps.json_mode in {
                "json_schema",
                "json_object",
            }:
                body["response_format"] = {"type": "json_object"}
        body.update(self._extra_body)
        return body

    def _adapt_to_rejection(self, body: dict[str, Any], error_text: str) -> bool:
        """Downgrade a capability the endpoint rejected. Returns True if adapted."""
        text = error_text.lower()
        caps = self._caps
        change: str | None = None

        if "response_format" in body and any(
            k in text for k in ("response_format", "json_schema", "json_object", "json mode")
        ):
            caps.json_mode = "json_object" if caps.json_mode == "json_schema" else "none"
            change = f"json_mode -> {caps.json_mode}"
        elif "tools" in body and any(k in text for k in ("tool", "function")):
            caps.native_tools = False
            change = "native_tools -> False"
        elif "temperature" in body and "temperature" in text:
            caps.supports_temperature = False
            change = "supports_temperature -> False"
        elif "max_tokens" in body and "max_completion_tokens" in text:
            caps.max_tokens_param = "max_completion_tokens"
            change = "max_tokens_param -> max_completion_tokens"
        elif caps.system_role and "system" in text and "role" in text:
            caps.system_role = False
            change = "system_role -> False"

        if change:
            logger.warning(
                "AI endpoint rejected a parameter; adapting: provider=%s model=%s change=%s",
                self._name,
                self._model,
                change,
            )
        return change is not None

    # --- Transport -------------------------------------------------------------

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        endpoint = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as http_client:
                    response = await http_client.post(endpoint, headers=headers, json=body)
            except httpx.TimeoutException as exc:
                raise AIConnectionError(
                    f"{self._label} request timed out after {self._timeout}s",
                    provider=self._name,
                    cause=exc,
                ) from exc
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                raise AIConnectionError(
                    f"Failed to connect to {self._label} at {self._base_url}: {exc}",
                    provider=self._name,
                    cause=exc,
                ) from exc
            except Exception as exc:
                raise AIProviderError(
                    f"{self._label} request failed unexpectedly: {exc}",
                    provider=self._name,
                    cause=exc,
                ) from exc

            if response.status_code in _RETRYABLE_STATUS and attempt < self._max_retries:
                delay = _retry_delay(response, attempt)
                logger.info(
                    "AI request retrying: provider=%s status=%s delay=%.1fs",
                    self._name,
                    response.status_code,
                    delay,
                )
                attempt += 1
                await asyncio.sleep(delay)
                continue
            return response

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        from app.ai.health import ai_health

        if not self.enabled:
            raise AIConfigurationError(
                f"{self._label} provider is not configured (missing {self._missing_config()})",
                provider=self._name,
            )

        logger.info(
            "AI request started: provider=%s, model=%s, tools=%d",
            self._name,
            self._model,
            len(tools or []),
        )

        try:
            for _ in range(_MAX_ADAPTATIONS + 1):
                body = self._build_body(messages, tools, response_format, temperature, max_tokens)
                response = await self._post(body)
                # Not 404: NIM answers "Function ... not found" for unknown models.
                if response.status_code in {400, 422} and self._adapt_to_rejection(
                    body, response.text
                ):
                    continue
                break

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise AIProviderError(
                    f"{self._label} HTTP error {exc.response.status_code}: {exc.response.text[:300]}",
                    provider=self._name,
                    cause=exc,
                ) from exc

            try:
                data = response.json()
            except ValueError as exc:
                raise AISchemaValidationError(
                    f"{self._label} returned a non-JSON response body",
                    provider=self._name,
                    cause=exc,
                ) from exc

            result = self._parse_completion(data)
        except AIProviderError as exc:
            ai_health.record_failure(self._name, self._model, exc)
            logger.warning("AI request failed: provider=%s, error=%s", self._name, exc)
            raise

        ai_health.record_success(self._name, self._model)
        logger.info(
            "AI request completed: provider=%s, model=%s, finish=%s, tool_calls=%d",
            self._name,
            self._model,
            result.finish_reason,
            len(result.tool_calls),
        )
        return result

    # --- Response parsing ------------------------------------------------------

    def _parse_completion(self, data: dict[str, Any]) -> ChatResult:
        choices = data.get("choices") or []
        if not choices:
            raise AISchemaValidationError(
                f"{self._label} returned no choices in completion response",
                provider=self._name,
            )
        choice = choices[0] or {}
        message = choice.get("message") or {}
        raw_content = message.get("content") or ""
        if isinstance(raw_content, list):  # content-parts format
            raw_content = "".join(p.get("text", "") for p in raw_content if isinstance(p, dict))

        content, inline_reasoning = split_reasoning(raw_content)
        reasoning = message.get("reasoning_content") or message.get("reasoning") or inline_reasoning

        tool_calls: list[ToolCallRequest] = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            if not name:
                continue
            args_raw = fn.get("arguments")
            args: dict[str, Any] = {}
            arg_error: str | None = None
            if isinstance(args_raw, dict):
                args = args_raw
            elif isinstance(args_raw, str) and args_raw.strip():
                try:
                    parsed = json.loads(args_raw)
                    if isinstance(parsed, dict):
                        args = parsed
                    else:
                        arg_error = "Tool arguments must be a JSON object"
                except json.JSONDecodeError as exc:
                    arg_error = f"Tool arguments were not valid JSON: {exc}"
            tool_calls.append(
                ToolCallRequest(
                    id=tc.get("id") or f"call_{i}",
                    name=name,
                    arguments=args,
                    argument_error=arg_error,
                )
            )

        if not content and not tool_calls:
            raise AISchemaValidationError(
                f"{self._label} returned empty message content",
                provider=self._name,
            )

        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            reasoning=reasoning if isinstance(reasoning, str) else None,
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage") or {},
        )


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), 20.0)
        except ValueError:
            pass
    return min(0.75 * (2**attempt), 8.0)
