"""One memory across conversations: a thread knows what other threads discussed."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema
from app.ai.providers.mock import MockProvider
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.user import User
from app.schemas.memory import MemoryExtractionResponse
from app.services import conversation_memory


class _Offline(MockProvider):
    @property
    def enabled(self) -> bool:
        return False


@pytest.fixture
def user(db: Session, user_id: int) -> User:
    return db.get(User, user_id)


def _capture(monkeypatch) -> list[str]:
    systems: list[str] = []

    def gen(*, system, prompt, schema):
        systems.append(system)
        return AgentResponseSchema(message="Noted.")

    monkeypatch.setattr(
        "app.agent.agent.get_ai_provider", lambda: MockProvider(default_response_generator=gen)
    )
    return systems


@pytest.mark.asyncio
async def test_new_conversation_knows_what_another_conversation_discussed(db, user, monkeypatch):
    agent = IrisAgent(default_registry)

    # Conversation A: startup (no AI, so the deterministic summary path runs).
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: _Offline())
    _, conv_a = await agent.run_turn(
        db, user, "For the startup we decided NEXUS pilot pricing is 15k per month for agencies"
    )
    assert "15k per month" in (db.get(AIConversation, conv_a.id).summary or "")

    # Conversation B: internship, a brand-new thread.
    systems = _capture(monkeypatch)
    _, conv_b = await agent.run_turn(db, user, "Help me plan my internship week")

    assert conv_b.id != conv_a.id
    shared = systems[0].split("SHARED MEMORY", 1)[1]
    assert "NEXUS pilot pricing is 15k per month" in shared
    assert f"#{conv_a.id}" in shared
    assert "ONE MEMORY" in systems[0]


@pytest.mark.asyncio
async def test_model_written_summary_and_topics_are_saved(db, user, monkeypatch):
    class Extractor(MockProvider):
        async def generate_structured(self, *, system, prompt, schema):
            if schema is MemoryExtractionResponse:
                assert "Previous conversation summary" in prompt
                return MemoryExtractionResponse(
                    conversation_summary="- Decided to pitch NEXUS to 10 agencies\n- Open: pricing",
                    topics=["startup outreach"],
                )
            return AgentResponseSchema(message="Plan saved.")

    provider = Extractor()
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)
    monkeypatch.setattr("app.ai.factory.get_ai_provider", lambda: provider)

    _, conv = await IrisAgent(default_registry).run_turn(db, user, "Let's pitch 10 agencies")

    saved = db.get(AIConversation, conv.id)
    assert saved.summary.startswith("- Decided to pitch NEXUS")
    assert saved.topics == ["startup outreach"]


def _old_thread(db, user, title, *messages):
    conv = AIConversation(user_id=user.id, title=title)
    db.add(conv)
    db.flush()
    for text in messages:
        db.add(AIMessage(conversation_id=conv.id, role="USER", content=text))
    db.commit()
    return conv


def test_threads_from_before_summaries_existed_are_still_shared(db, user):
    old = _old_thread(db, user, "Exam prep", "Compiler design exam is on 14 Oct")
    recent = conversation_memory.recent_conversations(db, user.id, user.timezone)
    assert recent[0]["conversation_id"] == old.id
    assert "Compiler design exam is on 14 Oct" in recent[0]["summary"]


def test_search_finds_older_threads_by_content_and_skips_current(db, user):
    target = _old_thread(db, user, "Misc", "Mentor suggested we raise a pre-seed round in March")
    current = _old_thread(db, user, "Today", "what about the pre-seed round?")

    hits = conversation_memory.search_conversations(
        db, user.id, user.timezone, "When do we raise the pre-seed round?", exclude_id=current.id
    )

    assert [h["conversation_id"] for h in hits] == [target.id]
    assert "pre-seed round in March" in hits[0]["matching_message"]


@pytest.mark.asyncio
async def test_conversation_tools(db, user):
    conv = _old_thread(db, user, "Startup pricing", "NEXUS pilot at 15k per month")

    res = await default_registry.execute("search_conversations", db, user, {"query": "pilot pricing"})
    assert res.success and res.data[0]["conversation_id"] == conv.id

    res = await default_registry.execute("get_conversation", db, user, {"conversation_id": conv.id})
    assert res.success and res.data["messages"][0]["content"] == "NEXUS pilot at 15k per month"

    res = await default_registry.execute("get_conversation", db, user, {"conversation_id": 99999})
    assert not res.success
