"""Provider Abstraction, OmniRoute, Gemini, Factory, and Architectural Tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import BaseModel

from app.ai.factory import create_ai_provider, set_ai_provider
from app.ai.provider import (
    AIConfigurationError,
    AIConnectionError,
    AIProvider,
    AIProviderError,
    AISchemaValidationError,
)
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.mock import MockProvider
from app.ai.providers.omniroute import OmniRouteProvider
from app.intelligence.decision_engine import decide_now
from app.intelligence.recommendation import DecisionType
from app.models.enums import LifeArea
from app.models.user import User
from tests.conftest import make_task


class SampleSchema(BaseModel):
    title: str
    score: int
    tags: list[str] = []


# --- OmniRoute Provider Tests -------------------------------------------------


@pytest.mark.asyncio
async def test_omniroute_successful_json_response():
    provider = OmniRouteProvider(
        base_url="http://localhost:20128/v1",
        api_key="test-key",
        model="auto/best-fast",
    )

    mock_response = httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": '{"title": "Deep Work", "score": 95, "tags": ["focus"]}'}}
            ]
        },
        request=httpx.Request("POST", "http://localhost:20128/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await provider.generate_structured(
            system="system prompt",
            prompt="user prompt",
            schema=SampleSchema,
        )

        assert isinstance(result, SampleSchema)
        assert result.title == "Deep Work"
        assert result.score == 95
        assert result.tags == ["focus"]


@pytest.mark.asyncio
async def test_omniroute_markdown_fenced_json_response():
    provider = OmniRouteProvider(base_url="http://localhost:20128/v1")

    mock_response = httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            "```json\n"
                            '{\n  "title": "Markdown Wrapped",\n'
                            '  "score": 88,\n  "tags": ["ai"]\n}\n'
                            "```"
                        )
                    }
                }
            ]
        },
        request=httpx.Request("POST", "http://localhost:20128/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await provider.generate_structured(
            system="system prompt",
            prompt="user prompt",
            schema=SampleSchema,
        )

        assert result.title == "Markdown Wrapped"
        assert result.score == 88


@pytest.mark.asyncio
async def test_omniroute_malformed_json_raises_schema_error():
    provider = OmniRouteProvider(base_url="http://localhost:20128/v1")

    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "Not a JSON document at all"}}]},
        request=httpx.Request("POST", "http://localhost:20128/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(AISchemaValidationError) as exc_info:
            await provider.generate_structured(
                system="system",
                prompt="prompt",
                schema=SampleSchema,
            )
        assert "not valid JSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_omniroute_schema_mismatch_raises_schema_error():
    provider = OmniRouteProvider(base_url="http://localhost:20128/v1")

    # Missing required 'score' field
    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"title": "Missing Score"}'}}]},
        request=httpx.Request("POST", "http://localhost:20128/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(AISchemaValidationError) as exc_info:
            await provider.generate_structured(
                system="system",
                prompt="prompt",
                schema=SampleSchema,
            )
        assert "failed schema validation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_omniroute_timeout_raises_connection_error():
    provider = OmniRouteProvider(base_url="http://localhost:20128/v1", timeout_seconds=1.0)

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timed out")

        with pytest.raises(AIConnectionError) as exc_info:
            await provider.generate_structured(
                system="system",
                prompt="prompt",
                schema=SampleSchema,
            )
        assert "timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_omniroute_connect_error_raises_connection_error():
    provider = OmniRouteProvider(base_url="http://localhost:20128/v1")

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(AIConnectionError) as exc_info:
            await provider.generate_structured(
                system="system",
                prompt="prompt",
                schema=SampleSchema,
            )
        assert "Failed to connect" in str(exc_info.value)


@pytest.mark.asyncio
async def test_omniroute_http_500_raises_provider_error():
    provider = OmniRouteProvider(base_url="http://localhost:20128/v1")

    mock_req = httpx.Request("POST", "http://localhost:20128/v1/chat/completions")
    mock_resp = httpx.Response(500, text="Internal Server Error", request=mock_req)

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with pytest.raises(AIProviderError) as exc_info:
            await provider.generate_structured(
                system="system",
                prompt="prompt",
                schema=SampleSchema,
            )
        assert "HTTP error 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_omniroute_empty_choices_raises_schema_error():
    provider = OmniRouteProvider(base_url="http://localhost:20128/v1")

    mock_response = httpx.Response(
        200,
        json={"choices": []},
        request=httpx.Request("POST", "http://localhost:20128/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(AISchemaValidationError):
            await provider.generate_structured(
                system="system",
                prompt="prompt",
                schema=SampleSchema,
            )


# --- Gemini Provider Tests ----------------------------------------------------


def test_gemini_enabled_property():
    p_disabled = GeminiProvider(api_key="")
    assert p_disabled.enabled is False

    p_enabled = GeminiProvider(api_key="fake-gemini-key")
    assert p_enabled.enabled is True
    assert p_enabled.name == "gemini"
    assert p_enabled.model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_gemini_disabled_raises_configuration_error():
    provider = GeminiProvider(api_key="")
    with pytest.raises(AIConfigurationError):
        await provider.generate_structured(
            system="system",
            prompt="prompt",
            schema=SampleSchema,
        )


# --- Factory & Configuration Switching Tests ----------------------------------


def test_factory_creates_omniroute_provider(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_provider", "omniroute")
    monkeypatch.setattr("app.core.config.settings.omniroute_base_url", "http://localhost:20128/v1")
    monkeypatch.setattr("app.core.config.settings.omniroute_model", "auto/best-fast")

    provider = create_ai_provider()
    assert isinstance(provider, OmniRouteProvider)
    assert provider.name == "omniroute"
    assert provider.model == "auto/best-fast"
    assert provider.enabled is True


def test_factory_creates_gemini_provider(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_provider", "gemini")
    monkeypatch.setattr("app.core.config.settings.gemini_api_key", "secret-key")
    monkeypatch.setattr("app.core.config.settings.gemini_model", "gemini-2.5-flash")

    provider = create_ai_provider()
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"
    assert provider.model == "gemini-2.5-flash"
    assert provider.enabled is True


def test_factory_creates_mock_provider(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_provider", "mock")

    provider = create_ai_provider()
    assert isinstance(provider, MockProvider)
    assert provider.name == "mock"
    assert provider.enabled is True


def test_factory_unsupported_provider_raises_configuration_error():
    with pytest.raises(AIConfigurationError) as exc_info:
        create_ai_provider("unknown-provider-xyz")
    assert "Unsupported AI provider" in str(exc_info.value)


# --- Architectural Provider-Independence Test --------------------------------


@pytest.mark.asyncio
async def test_architectural_provider_independence(db, user_id):
    """Proves that the Decision Engine and Reasoning flow work identically across
    different AI providers (MockProviderA vs MockProviderB) without changing any
    business logic.
    """
    user = db.query(User).filter(User.id == user_id).first()
    task = make_task(db, user_id, title="Sprint task", area=LifeArea.STARTUP.value)

    # Provider A: OmniRoute-style mock
    class MockProviderA(AIProvider):
        @property
        def name(self) -> str:
            return "provider-alpha"

        @property
        def model(self) -> str:
            return "model-alpha-v1"

        @property
        def enabled(self) -> bool:
            return True

        async def generate_structured(self, *, system: str, prompt: str, schema: type[BaseModel]):
            return schema(
                recommendation_type="TASK",
                decision_type=DecisionType.MUST_DO,
                decision="STARTUP_EXECUTION",
                task_id=task.id,
                title="Sprint task via Alpha",
                reason="Alpha provider evaluated startup urgency.",
                confidence=0.92,
            )

    # Provider B: Gemini/Anthropic-style mock with different model metadata
    class MockProviderB(AIProvider):
        @property
        def name(self) -> str:
            return "provider-beta"

        @property
        def model(self) -> str:
            return "model-beta-pro"

        @property
        def enabled(self) -> bool:
            return True

        async def generate_structured(self, *, system: str, prompt: str, schema: type[BaseModel]):
            return schema(
                recommendation_type="TASK",
                decision_type=DecisionType.MUST_DO,
                decision="STARTUP_EXECUTION",
                task_id=task.id,
                title="Sprint task via Beta",
                reason="Beta provider evaluated startup urgency.",
                confidence=0.95,
            )

    # Execute through same Decision Engine with Provider A
    set_ai_provider(MockProviderA())
    res_a, src_a = await decide_now(db, user, available_minutes=60)
    assert src_a == "AI"
    assert res_a.title == "Sprint task via Alpha"
    assert res_a.task_id == task.id
    assert res_a.confidence == pytest.approx(0.92)

    # Execute through same Decision Engine with Provider B
    set_ai_provider(MockProviderB())
    res_b, src_b = await decide_now(db, user, available_minutes=60)
    assert src_b == "AI"
    assert res_b.title == "Sprint task via Beta"
    assert res_b.task_id == task.id
    assert res_b.confidence == pytest.approx(0.95)
