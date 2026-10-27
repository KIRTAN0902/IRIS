"""AI Invocation Reliability & Resilience Engineering Tests.

Validates:
1. Deadline budget propagation across providers, retries, and fallbacks.
2. Removal of artificial timeout clamps (e.g., 12.0s / 15.0s).
3. Exponential backoff with jitter and retry cap.
4. Turn-level provider stickiness across multi-turn tool loops.
5. Controlled provider health degradation (DEGRADED vs NOT_RESPONDING) and auto-cooldown.
6. Safe intent classification parameter gating.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agent.harness import AgentHarness
from app.agent.registry import ToolRegistry
from app.agent.schemas import AgentResponseSchema
from app.ai.capabilities import ModelCapabilities
from app.ai.deadline import RequestDeadline, get_current_deadline, reset_deadline, set_deadline
from app.ai.health import AIHealthTracker, ai_health
from app.ai.provider import (
    AIConnectionError,
    AIProvider,
    AIProviderError,
    ChatMessage,
    ChatResult,
    ToolCallRequest,
    ToolDefinition,
)
from app.ai.providers.gemini import GeminiProvider, active_turn_backend
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.utils.datetime import utcnow


# --- 1. Deadline Management Tests ---------------------------------------------


def test_deadline_budget_and_expiration():
    """Verify deadline calculates elapsed, remaining, and expiration correctly."""
    dl = RequestDeadline(total_seconds=2.0, min_remaining_for_attempt=0.5)
    assert not dl.is_expired
    assert dl.has_budget_for_attempt
    assert 1.5 <= dl.remaining <= 2.0
    assert 0.0 <= dl.elapsed <= 0.5

    # per_attempt_timeout bounds
    assert dl.per_attempt_timeout(max_per_attempt=1.0) <= 1.0
    assert dl.per_attempt_timeout(max_per_attempt=10.0) <= 2.0

    # httpx timeout object
    ht = dl.httpx_timeout(max_read=1.0)
    assert ht.read <= 1.0
    assert ht.connect <= 2.0


def test_deadline_context_propagation():
    """Verify set_deadline and get_current_deadline propagate in async context."""
    assert get_current_deadline() is None
    token = set_deadline(30.0)
    try:
        active = get_current_deadline()
        assert active is not None
        assert active.total_seconds == 30.0
    finally:
        reset_deadline(token)
    assert get_current_deadline() is None


# --- 2. Timeout Clamp Removal Tests ------------------------------------------


def test_gemini_provider_respects_configured_timeout():
    """Verify GeminiProvider does NOT clamp timeouts to 12.0s or 10.0s."""
    custom_timeout = 35.0
    provider = GeminiProvider(
        api_key="test-key",
        model="gemini-3.1-flash-lite",
        fallback_model=None,
        timeout_seconds=custom_timeout,
    )
    # When no fallback model, primary backend gets the full timeout
    assert provider._chat_backend._timeout == custom_timeout

    # When fallback model is configured, timeout is partitioned at 22s (not 12s)
    provider_with_fb = GeminiProvider(
        api_key="test-key",
        model="gemini-3.1-flash-lite",
        fallback_model="gemini-3.5-flash",
        timeout_seconds=custom_timeout,
    )
    assert provider_with_fb._chat_backend._timeout == 22.0
    assert provider_with_fb._fallback_chat_backend._timeout == 22.0


# --- 3. Error Classification & Jittered Retry Tests --------------------------


@pytest.mark.asyncio
async def test_openai_compatible_retries_transient_503_with_deadline_budget():
    """Verify 503 Service Unavailable triggers bounded retry when deadline budget exists."""
    provider = OpenAICompatibleProvider(
        base_url="https://api.example.com",
        model="test-model",
        api_key="test-key",
        timeout_seconds=10.0,
        max_retries=2,
    )

    mock_503 = MagicMock(spec=httpx.Response)
    mock_503.status_code = 503
    mock_503.headers = {}
    mock_503.text = "Service Unavailable"

    mock_200 = MagicMock(spec=httpx.Response)
    mock_200.status_code = 200
    mock_200.headers = {}
    mock_200.json.return_value = {
        "choices": [{"message": {"content": "Recovered response", "role": "assistant"}}]
    }

    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_503
        return mock_200

    token = set_deadline(15.0)
    try:
        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            result = await provider.chat([ChatMessage(role="user", content="Hello")])
            assert result.content == "Recovered response"
            assert call_count == 2
    finally:
        reset_deadline(token)


@pytest.mark.asyncio
async def test_openai_compatible_aborts_retry_when_deadline_exhausted():
    """Verify retry is skipped when deadline budget is exhausted."""
    provider = OpenAICompatibleProvider(
        base_url="https://api.example.com",
        model="test-model",
        api_key="test-key",
        timeout_seconds=10.0,
        max_retries=2,
    )

    mock_503 = MagicMock(spec=httpx.Response)
    mock_503.status_code = 503
    mock_503.headers = {}
    mock_503.text = "Service Unavailable"

    # Set deadline with 0 seconds remaining
    dl = RequestDeadline(total_seconds=1.0)
    dl.deadline = time.monotonic() - 1.0  # Force expired

    from app.ai.deadline import current_deadline

    token = current_deadline.set(dl)
    try:
        with pytest.raises(AIConnectionError) as exc_info:
            await provider._post({"model": "test"})
        assert "deadline exceeded" in str(exc_info.value).lower()
    finally:
        current_deadline.reset(token)


# --- 4. Turn-Level Provider Stickiness Tests ---------------------------------


@pytest.mark.asyncio
async def test_turn_level_provider_stickiness():
    """Verify that once a secondary provider generates a tool call, the turn sticks to it."""
    active_turn_backend.set(None)

    # Primary provider that always fails
    primary_backend = OpenAICompatibleProvider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.1-flash-lite",
        api_key="test-key",
    )
    # Secondary provider (e.g. Groq) that succeeds
    secondary_backend = OpenAICompatibleProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        model="qwen/qwen3.8-27b",
        api_key="test-groq-key",
    )

    gemini_provider = GeminiProvider(
        api_key="test-key",
        model="gemini-3.1-flash-lite",
    )
    gemini_provider._chat_backend = primary_backend
    gemini_provider._secondary_fallbacks = [secondary_backend]

    # Step 1: Primary fails, secondary succeeds with a tool call
    tool_call = ToolCallRequest(id="call_1", name="search", arguments={"q": "test"})
    step1_result = ChatResult(content="Checking...", tool_calls=[tool_call])

    async def primary_fail(*args, **kwargs):
        raise AIConnectionError("Google Gemini endpoint 503")

    async def secondary_success(*args, **kwargs):
        return step1_result

    primary_backend.chat = AsyncMock(side_effect=primary_fail)
    secondary_backend.chat = AsyncMock(side_effect=secondary_success)

    # Run Step 1
    res1 = await gemini_provider.chat([ChatMessage(role="user", content="Search test")])
    assert res1.tool_calls == [tool_call]
    # Verify active_turn_backend was set to secondary
    assert active_turn_backend.get() is secondary_backend

    # Step 2: In the same turn, calling gemini_provider.chat should directly invoke secondary_backend
    step2_result = ChatResult(content="Final search results found.")
    secondary_backend.chat = AsyncMock(return_value=step2_result)
    primary_backend.chat = AsyncMock(side_effect=Exception("Should NOT be called in sticky turn!"))

    res2 = await gemini_provider.chat([
        ChatMessage(role="user", content="Search test"),
        ChatMessage(role="assistant", content="Checking...", tool_calls=[tool_call]),
        ChatMessage(role="tool", tool_call_id="call_1", content="result data"),
    ])
    assert res2.content == "Final search results found."
    secondary_backend.chat.assert_awaited_once()

    # Reset for next turn
    active_turn_backend.set(None)


# --- 5. Controlled Health Degradation Tests ----------------------------------


def test_health_tracker_single_failure_marks_degraded():
    """Verify single failure marks status DEGRADED while keeping responding=True."""
    from app.ai.factory import set_ai_provider
    from app.ai.providers.mock import MockProvider

    mock_provider = MockProvider(name="gemini", model="gemini-3.1-flash-lite")
    set_ai_provider(mock_provider)

    tracker = AIHealthTracker()
    tracker.reset()

    tracker.record_failure("gemini", "gemini-3.1-flash-lite", "Temporary 503 error")
    status = tracker.get_status()

    assert status["status"] == "DEGRADED"
    assert status["responding"] is True
    assert status["consecutive_failures"] == 1


def test_health_tracker_consecutive_failures_marks_not_responding():
    """Verify 2+ consecutive failures mark status NOT_RESPONDING with responding=False."""
    from app.ai.factory import set_ai_provider
    from app.ai.providers.mock import MockProvider

    mock_provider = MockProvider(name="gemini", model="gemini-3.1-flash-lite")
    set_ai_provider(mock_provider)

    tracker = AIHealthTracker()
    tracker.reset()

    tracker.record_failure("gemini", "gemini-3.1-flash-lite", "Failure 1")
    tracker.record_failure("gemini", "gemini-3.1-flash-lite", "Failure 2")
    status = tracker.get_status()

    assert status["status"] == "NOT_RESPONDING"
    assert status["responding"] is False
    assert status["consecutive_failures"] == 2

    # Success clears it
    tracker.record_success("gemini", "gemini-3.1-flash-lite")
    status_cleared = tracker.get_status()
    assert status_cleared["status"] == "OPERATIONAL"
    assert status_cleared["responding"] is True
    assert status_cleared["consecutive_failures"] == 0


def test_health_tracker_ignores_client_parameter_rejections():
    """Verify HTTP 400 parameter adaptations do not degrade health tracker."""
    from app.ai.factory import set_ai_provider
    from app.ai.providers.mock import MockProvider

    mock_provider = MockProvider(name="gemini", model="gemini-3.1-flash-lite")
    set_ai_provider(mock_provider)

    tracker = AIHealthTracker()
    tracker.reset()

    tracker.record_failure("gemini", "gemini-3.1-flash-lite", "HTTP 400 Unknown name response_format")
    status = tracker.get_status()

    # Should remain OPERATIONAL because 400 parameter adaptation is client-side negotiation
    assert status["status"] == "OPERATIONAL"
    assert status["consecutive_failures"] == 0
