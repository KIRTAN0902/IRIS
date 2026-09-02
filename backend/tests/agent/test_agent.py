"""Tests for the IrisAgent conversational loop and intent execution."""

import pytest
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema, ToolCall
from app.ai.providers.mock import MockProvider
from app.models.task import Task
from app.models.user import User


@pytest.fixture
def test_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "founder@iris.local").first()
    if not user:
        user = User(
            email="founder@iris.local",
            name="Kirtan Founder",
            timezone="Asia/Kolkata",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_agent_information_turn(db: Session, test_user: User, monkeypatch):
    mock_resp = AgentResponseSchema(
        thought="User is asking what's important today.",
        actions=[],
        message="Your main priority today is the Compiler Design assignment due at 6:00 PM.",
        actions_summary=[],
        evidence=["College deadline: 6:00 PM", "Available flexible time: 120m"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, conv = await agent.run_turn(
        db=db,
        user=test_user,
        user_message="What should I focus on today?",
    )

    assert out.role == "ASSISTANT"
    assert "Compiler Design" in out.content
    assert len(out.evidence) > 0
    assert conv.id == out.conversation_id


@pytest.mark.asyncio
async def test_agent_action_turn(db: Session, test_user: User, monkeypatch):
    mock_resp = AgentResponseSchema(
        thought="User wants to add a college assignment.",
        actions=[
            ToolCall(
                tool_name="create_task",
                parameters={
                    "title": "Machine Learning Lab 4",
                    "area": "COLLEGE",
                    "priority": "HIGH",
                    "estimated_duration": 60,
                },
            )
        ],
        message="I have added 'Machine Learning Lab 4' to your College tasks with high priority.",
        actions_summary=["Added 'Machine Learning Lab 4'"],
        evidence=["Priority: HIGH", "Estimated: 60m"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, conv = await agent.run_turn(
        db=db,
        user=test_user,
        user_message="Add Machine Learning Lab 4 task.",
    )

    assert out.role == "ASSISTANT"
    assert len(out.actions_taken) == 1
    assert out.actions_taken[0]["tool_name"] == "create_task"
    assert out.actions_taken[0]["success"] is True

    # Verify task was actually persisted in database
    task = (
        db.query(Task)
        .filter(Task.title == "Machine Learning Lab 4", Task.user_id == test_user.id)
        .first()
    )
    assert task is not None
    assert task.area == "COLLEGE"


@pytest.mark.asyncio
async def test_agent_deterministic_fallback(db: Session, test_user: User, monkeypatch):
    class OfflineProvider(MockProvider):
        @property
        def enabled(self) -> bool:
            return False

    mock_provider = OfflineProvider()
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, conv = await agent.run_turn(
        db=db,
        user=test_user,
        user_message="What should I do right now?",
    )

    assert out.role == "ASSISTANT"
    assert out.source == "DETERMINISTIC"
    assert len(out.content) > 0
