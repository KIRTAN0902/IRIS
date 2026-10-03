"""Tests for IRIS conversational memory across multiple turns and threads."""

import pytest
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema, ToolCall
from app.ai.providers.mock import MockProvider
from app.models.ai_memory import AIMemory
from app.models.user import User
from app.services.memory_service import memory_service


@pytest.fixture
def agent_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "founder_mem_agent@iris.local").first()
    if not user:
        user = User(
            email="founder_mem_agent@iris.local",
            name="Kirtan Founder Memory",
            timezone="Asia/Kolkata",
            facts={},
            preferences={},
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_agent_save_memory_tool(db: Session, agent_user: User, monkeypatch):
    """Verify agent can explicitly invoke save_memory tool."""
    mock_resp = AgentResponseSchema(
        thought="User gave me an instruction to remember; calling save_memory.",
        actions=[
            ToolCall(
                tool_name="save_memory",
                parameters={
                    "content": "User prefers no work blocks after 9:30 PM",
                    "category": "CONSTRAINT",
                    "key": "night_cutoff",
                    "importance": 0.95,
                },
            )
        ],
        message="I've noted that constraint. I will ensure no work is scheduled past 9:30 PM.",
        actions_summary=["Saved constraint to memory"],
        evidence=["User night cutoff: 9:30 PM"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, conv = await agent.run_turn(
        db=db,
        user=agent_user,
        user_message="Make sure you never schedule work after 9:30 PM.",
    )

    assert out.role == "ASSISTANT"
    assert len(out.actions_taken) == 1
    assert out.actions_taken[0]["tool_name"] == "save_memory"
    assert out.actions_taken[0]["success"] is True

    # Check that memory was created in DB
    mem = (
        db.query(AIMemory)
        .filter(AIMemory.user_id == agent_user.id, AIMemory.key == "night_cutoff")
        .first()
    )
    assert mem is not None
    assert "9:30 PM" in mem.content
    assert mem.category == "CONSTRAINT"


@pytest.mark.asyncio
async def test_cross_conversation_memory_recall(db: Session, agent_user: User, monkeypatch):
    """Test memory persistence across separate conversation threads.
    Thread A: User establishes a key fact.
    Thread B: User in a NEW conversation asks about it -> prompt includes the recalled memory.
    """
    # 1. Store a memory for agent_user
    memory_service.store_memory(
        db=db,
        user=agent_user,
        content="Co-founder is Alex; Nexus is targeting cosmetic dentists for appointment automation",
        category="PROJECT",
        key="nexus_dentist_focus",
        importance=0.9,
    )

    # 2. In Thread B, user asks "Who is my co-founder and what is our target for Nexus?"
    captured_system_prompts: list[str] = []

    class CapturingMockProvider(MockProvider):
        async def generate_structured(self, system, prompt, schema):
            captured_system_prompts.append(system)
            return AgentResponseSchema(
                thought="Found in memory that Alex is cofounder and targeting cosmetic dentists.",
                actions=[],
                message="Your co-founder is Alex, and Nexus is focused on targeting cosmetic dentists for appointment automation.",
                actions_summary=[],
                evidence=["Recalled from memory: Alex, cosmetic dentists"],
            )

    capturing_provider = CapturingMockProvider()
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: capturing_provider)

    agent = IrisAgent(default_registry)
    out, conv2 = await agent.run_turn(
        db=db,
        user=agent_user,
        user_message="Who is my co-founder and what is our target for Nexus?",
        conversation_id=None,  # Brand new conversation!
    )

    assert out.role == "ASSISTANT"
    assert "Alex" in out.content
    assert "cosmetic dentists" in out.content

    # Verify system prompt in Thread B received the memory from the memory service
    assert len(captured_system_prompts) > 0
    sys_prompt = captured_system_prompts[0]
    assert "STORED USER MEMORY & CONTEXT" in sys_prompt
    assert "Alex" in sys_prompt or "dentists" in sys_prompt


@pytest.mark.asyncio
async def test_deterministic_memory_recall_and_save(db: Session, agent_user: User, monkeypatch):
    """Verify memory queries and commands work in deterministic fallback mode."""
    class OfflineProvider(MockProvider):
        @property
        def enabled(self) -> bool:
            return False

    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: OfflineProvider())

    agent = IrisAgent(default_registry)

    # Turn 1: Explicit command to remember
    out1, conv1 = await agent.run_turn(
        db=db,
        user=agent_user,
        user_message="Remember that my main focus is customer interviews this week.",
    )
    assert out1.source == "DETERMINISTIC"
    assert "stored this to memory" in out1.content.lower() or "committed this to memory" in out1.content.lower()

    # Turn 2: Query what IRIS remembers
    out2, conv2 = await agent.run_turn(
        db=db,
        user=agent_user,
        user_message="What do you remember about my focus?",
    )
    assert out2.source == "DETERMINISTIC"
    assert "customer interviews" in out2.content.lower()
