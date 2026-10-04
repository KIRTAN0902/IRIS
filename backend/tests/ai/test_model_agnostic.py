"""Model-agnostic provider layer: capabilities, output normalisation, adaptation, presets."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import BaseModel

from app.agent.tools.tasks import GetTasksParams
from app.ai.capabilities import resolve_capabilities
from app.ai.factory import create_ai_provider
from app.ai.provider import ChatMessage, ToolDefinition
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.structured import compact_schema, extract_json, split_reasoning

URL = "https://llm.example.com/v1"


class SampleSchema(BaseModel):
    title: str
    score: int


def _resp(status: int, payload: dict | None = None, text: str | None = None, headers=None):
    req = httpx.Request("POST", f"{URL}/chat/completions")
    if payload is not None:
        return httpx.Response(status, json=payload, request=req, headers=headers)
    return httpx.Response(status, text=text or "", request=req, headers=headers)


def _content(text: str) -> dict:
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}


def _provider(model: str = "some-new-model", **kw) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(base_url=URL, model=model, api_key="k", **kw)


# --- Capabilities ------------------------------------------------------------


def test_capabilities_unknown_model_gets_defaults():
    caps = resolve_capabilities("acme/brand-new-model-9000")
    assert caps.native_tools is True
    assert caps.json_mode == "json_object"


def test_capabilities_profiles_match_vendor_prefixed_ids():
    nemotron = resolve_capabilities("nvidia/nemotron-3-super-120b-a12b")
    assert nemotron.reasoning is True
    assert nemotron.json_mode == "none"

    gpt5 = resolve_capabilities("openai/gpt-5-mini")
    assert gpt5.supports_temperature is False
    assert gpt5.max_tokens_param == "max_completion_tokens"


def test_capabilities_env_overrides_win():
    caps = resolve_capabilities("nvidia/nemotron-x", {"native_tools": False, "bogus": 1})
    assert caps.native_tools is False
    assert caps.reasoning is True


# --- Output normalisation ------------------------------------------------------


def test_split_reasoning_handles_think_blocks():
    answer, reasoning = split_reasoning("<think>weigh options</think>\nFinal answer.")
    assert answer == "Final answer."
    assert reasoning == "weigh options"

    answer, reasoning = split_reasoning("hidden thoughts</think>Visible")
    assert answer == "Visible"
    assert reasoning == "hidden thoughts"


def test_extract_json_from_noisy_output():
    assert extract_json('<think>{"no": 1}</think>```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": {"b": "}"}} hope that helps') == {"a": {"b": "}"}}


def test_compact_schema_inlines_refs_and_optionals():
    schema = compact_schema(GetTasksParams)
    dumped = json.dumps(schema)
    assert "$ref" not in dumped and "$defs" not in dumped
    assert "COLLEGE" in json.dumps(schema["properties"]["area"])
    assert "anyOf" not in schema["properties"]["area"]


# --- Request shaping & runtime adaptation --------------------------------------


@pytest.mark.asyncio
async def test_request_shaped_by_capabilities():
    provider = _provider("gpt-5-mini")
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post:
        post.return_value = _resp(200, _content("hi"))
        await provider.chat([ChatMessage(role="user", content="hello")])
        body = post.call_args.kwargs["json"]
    assert "max_completion_tokens" in body and "max_tokens" not in body
    assert "temperature" not in body


@pytest.mark.asyncio
async def test_tool_calls_and_reasoning_are_parsed():
    provider = _provider()
    payload = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "reasoning_content": "Need the task list first.",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "get_tasks", "arguments": '{"limit": 5}'},
                        },
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {"name": "create_task", "arguments": "{oops"},
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    tools = [ToolDefinition(name="get_tasks", description="List tasks")]
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post:
        post.return_value = _resp(200, payload)
        result = await provider.chat([ChatMessage(role="user", content="x")], tools=tools)
        assert post.call_args.kwargs["json"]["tools"][0]["function"]["name"] == "get_tasks"

    assert result.reasoning == "Need the task list first."
    assert [c.name for c in result.tool_calls] == ["get_tasks", "create_task"]
    assert result.tool_calls[0].arguments == {"limit": 5}
    assert result.tool_calls[1].argument_error is not None


@pytest.mark.asyncio
async def test_rejected_tools_parameter_is_downgraded_and_retried():
    provider = _provider()
    tools = [ToolDefinition(name="get_tasks", description="List tasks")]
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post:
        post.side_effect = [
            _resp(400, text='{"error": "This model does not support tools"}'),
            _resp(200, _content("plain answer")),
        ]
        result = await provider.chat([ChatMessage(role="user", content="x")], tools=tools)
        assert "tools" in post.call_args_list[0].kwargs["json"]
        assert "tools" not in post.call_args_list[1].kwargs["json"]

    assert result.content == "plain answer"
    assert provider.capabilities.native_tools is False


@pytest.mark.asyncio
async def test_rejected_response_format_degrades_json_mode():
    provider = _provider("gpt-4o-mini")
    assert provider.capabilities.json_mode == "json_schema"
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post:
        post.side_effect = [
            _resp(400, text="response_format json_schema is not supported"),
            _resp(200, _content('{"title": "A", "score": 1}')),
        ]
        out = await provider.generate_structured(system="s", prompt="p", schema=SampleSchema)
    assert out.title == "A"
    assert provider.capabilities.json_mode == "json_object"


@pytest.mark.asyncio
async def test_transient_errors_are_retried():
    provider = _provider()
    with (
        patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post,
        patch("app.ai.providers.openai_compatible.asyncio.sleep", new_callable=AsyncMock),
    ):
        post.side_effect = [
            _resp(429, text="rate limited", headers={"retry-after": "1"}),
            _resp(200, _content("ok")),
        ]
        result = await provider.chat([ChatMessage(role="user", content="x")])
    assert result.content == "ok"
    assert post.call_count == 2


@pytest.mark.asyncio
async def test_structured_output_is_repaired_by_the_model():
    provider = _provider("nvidia/nemotron-x")
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post:
        post.side_effect = [
            _resp(200, _content('<think>hmm</think>{"title": "A"}')),  # missing "score"
            _resp(200, _content('{"title": "A", "score": 7}')),
        ]
        out = await provider.generate_structured(system="s", prompt="p", schema=SampleSchema)
        repair_msgs = post.call_args_list[1].kwargs["json"]["messages"]

    assert out.score == 7
    assert "could not be used" in repair_msgs[-1]["content"]


@pytest.mark.asyncio
async def test_system_role_unsupported_is_merged_into_user():
    provider = _provider(capability_overrides={"system_role": False})
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as post:
        post.return_value = _resp(200, _content("ok"))
        await provider.chat(
            [ChatMessage(role="system", content="RULES"), ChatMessage(role="user", content="hi")]
        )
        msgs = post.call_args.kwargs["json"]["messages"]
    assert [m["role"] for m in msgs] == ["user"]
    assert msgs[0]["content"].startswith("RULES")


# --- Factory presets -------------------------------------------------------------


def test_factory_generic_settings_select_any_backend(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_model", "anthropic/claude-sonnet-4.5")
    monkeypatch.setattr("app.core.config.settings.ai_api_key", "sk-or-test")
    provider = create_ai_provider("openrouter")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.model == "anthropic/claude-sonnet-4.5"
    assert provider.enabled is True


def test_factory_ai_model_overrides_legacy_vendor_model(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.nvidia_api_key", "nvapi-test")
    monkeypatch.setattr("app.core.config.settings.ai_model", "meta/llama-3.3-70b-instruct")
    provider = create_ai_provider("nvidia")
    assert provider.model == "meta/llama-3.3-70b-instruct"
    assert provider.capabilities.context_window == 131_072


def test_factory_local_servers_need_no_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_model", "qwen3:8b")
    provider = create_ai_provider("ollama")
    assert provider.enabled is True
    assert provider.capabilities.reasoning is True


def test_factory_custom_endpoint_requires_base_url(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_model", "my-model")
    assert create_ai_provider("openai_compatible").enabled is False
    monkeypatch.setattr("app.core.config.settings.ai_base_url", "http://gpu-box:8000/v1")
    assert create_ai_provider("openai_compatible").enabled is True


def test_factory_capability_overrides_from_env(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_model", "whatever")
    monkeypatch.setattr("app.core.config.settings.ai_api_key", "k")
    monkeypatch.setattr(
        "app.core.config.settings.ai_capabilities",
        '{"native_tools": false, "context_window": 8000}',
    )
    caps = create_ai_provider("openai").capabilities
    assert caps.native_tools is False
    assert caps.history_messages == 6


def test_fast_turn_applies_the_models_fast_body_only_when_set():
    from app.ai.provider import ChatMessage, fast_turn

    p = _provider("nvidia/nemotron-3-ultra-550b-a55b")
    msgs = [ChatMessage(role="user", content="hi")]
    assert "chat_template_kwargs" not in p._build_body(msgs, None, None, None, None)

    token = fast_turn.set(True)
    try:
        body = p._build_body(msgs, None, None, None, None)
    finally:
        fast_turn.reset(token)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}

    # Models without a fast_body are untouched.
    token = fast_turn.set(True)
    try:
        assert "chat_template_kwargs" not in _provider("gpt-4o-mini")._build_body(msgs, None, None, None, None)
    finally:
        fast_turn.reset(token)


def test_rejected_fast_body_is_dropped():
    from app.ai.provider import ChatMessage, fast_turn

    p = _provider("nvidia/nemotron-3-ultra-550b-a55b")
    token = fast_turn.set(True)
    try:
        body = p._build_body([ChatMessage(role="user", content="hi")], None, None, None, None)
        assert p._adapt_to_rejection(body, "Unknown field: chat_template_kwargs") is True
        assert "chat_template_kwargs" not in p._build_body([ChatMessage(role="user", content="hi")], None, None, None, None)
    finally:
        fast_turn.reset(token)
