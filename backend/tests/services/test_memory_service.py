"""Tests for MemoryService (storage, deduplication, search ranking, and extraction)."""

import pytest
from sqlalchemy.orm import Session

from app.models.ai_memory import AIMemory
from app.models.user import User
from app.schemas.memory import ExtractedMemoryItem, MemoryExtractionResponse
from app.services.memory_service import memory_service


@pytest.fixture
def memory_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "memory_tester@iris.local").first()
    if not user:
        user = User(
            email="memory_tester@iris.local",
            name="Memory Tester",
            timezone="Asia/Kolkata",
            facts={},
            preferences={},
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def test_store_and_deduplicate_memory(db: Session, memory_user: User):
    # Store initial memory
    mem1 = memory_service.store_memory(
        db=db,
        user=memory_user,
        content="User prefers deep work in mornings before 10 AM",
        category="PREFERENCE",
        key="deep_work_time",
        importance=0.8,
    )
    assert mem1.id is not None
    assert mem1.key == "deep_work_time"
    assert mem1.category == "PREFERENCE"

    # Store updated memory with same key -> should update instead of creating duplicate
    mem2 = memory_service.store_memory(
        db=db,
        user=memory_user,
        content="User prefers deep work in mornings before 11 AM (extended)",
        category="PREFERENCE",
        key="deep_work_time",
        importance=0.9,
    )
    assert mem2.id == mem1.id
    assert "11 AM" in mem2.content

    # Verify user preferences were synced
    db.refresh(memory_user)
    assert memory_user.preferences.get("deep_work_time") == "User prefers deep work in mornings before 11 AM (extended)"

    # Total memories should be 1
    count = db.query(AIMemory).filter(AIMemory.user_id == memory_user.id).count()
    assert count == 1


def test_search_relevant_memories(db: Session, memory_user: User):
    memory_service.store_memory(
        db=db,
        user=memory_user,
        content="Nexus is targeting boutique marketing agencies with 10-30 staff",
        category="PROJECT",
        key="nexus_target_audience",
        importance=0.9,
    )
    memory_service.store_memory(
        db=db,
        user=memory_user,
        content="Compiler Design lab assignment due every Friday",
        category="FACT",
        key="compiler_lab_day",
        importance=0.7,
    )

    # Search for "marketing"
    results = memory_service.search_relevant_memories(
        db=db, user_id=memory_user.id, query="What marketing agencies are we targeting?", limit=5
    )
    assert len(results) >= 1
    assert "Nexus is targeting boutique marketing agencies" in results[0].content
    assert results[0].access_count >= 1

    # Search for "compiler"
    results_comp = memory_service.search_relevant_memories(
        db=db, user_id=memory_user.id, query="Tell me about compiler design deadlines", limit=5
    )
    assert len(results_comp) >= 1
    assert "Compiler Design" in results_comp[0].content


def test_heuristic_memory_extraction(db: Session, memory_user: User):
    text = "Remember that my co-founder is Alex and Nexus is pivoting to dentists"
    extracted = memory_service._heuristic_extract(text)
    assert len(extracted) >= 1
    assert any("Alex" in item["content"] or "Dentists" in item["content"] for item in extracted)


@pytest.mark.asyncio
async def test_extract_and_store_from_conversation_mock(db: Session, memory_user: User, monkeypatch):
    class MockExtractionProvider:
        name = "mock"
        model = "mock-1"
        enabled = True

        async def generate_structured(self, system, prompt, schema):
            return MemoryExtractionResponse(
                memories=[
                    ExtractedMemoryItem(
                        content="Prefers 45-minute focus intervals over 90-minute intervals",
                        category="PREFERENCE",
                        key="pomodoro_duration",
                        importance=0.85,
                    )
                ]
            )

    monkeypatch.setattr("app.ai.factory.get_ai_provider", lambda: MockExtractionProvider())

    stored = await memory_service.extract_and_store_from_conversation(
        db=db,
        user=memory_user,
        user_message="I tried 90-minute blocks today but 45-minute focus intervals work much better for me.",
        assistant_message="Noted. I'll structure your focus sessions in 45-minute sprints.",
    )

    assert len(stored) == 1
    assert stored[0].key == "pomodoro_duration"
    assert "45-minute focus intervals" in stored[0].content


def test_delete_memory(db: Session, memory_user: User):
    mem = memory_service.store_memory(
        db=db,
        user=memory_user,
        content="Temporary reminder to call dentist tomorrow",
        category="FACT",
        importance=0.5,
    )
    mem_id = mem.id
    assert memory_service.delete_memory(db, memory_user.id, mem_id) is True
    assert db.query(AIMemory).filter(AIMemory.id == mem_id).first() is None
