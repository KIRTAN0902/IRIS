from __future__ import annotations

from sqlalchemy.orm import Session

from app.knowledge.migration import migrate_memories_to_knowledge
from app.knowledge.service import knowledge_service
from app.models.ai_memory import AIMemory
from app.models.knowledge import KnowledgeClaim, KnowledgeSource


def _memory(db: Session, user_id: int, **overrides) -> AIMemory:
    defaults = {
        "user_id": user_id,
        "category": "FACT",
        "key": "primary_database",
        "content": "The primary database is PostgreSQL.",
        "importance": 0.8,
        "confidence": 0.9,
        "source": "USER_EXPLICIT",
        "is_active": True,
    }
    defaults.update(overrides)
    memory = AIMemory(**defaults)
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def test_dry_run_reports_without_writing(db: Session, user_id: int):
    _memory(db, user_id)
    before = db.query(KnowledgeClaim).count()
    result = migrate_memories_to_knowledge(db, user_id=user_id, dry_run=True)
    assert result["dry_run"] is True
    assert result["would_migrate"] == 1
    assert db.query(KnowledgeClaim).count() == before


def test_migration_is_additive_and_idempotent(db: Session, user_id: int):
    memory = _memory(db, user_id)
    legacy_content = memory.content

    first = migrate_memories_to_knowledge(db, user_id=user_id)
    assert first["migrated"] == 1
    assert first["failed"] == 0
    assert first["legacy_memory_modified"] is False

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.user_id == user_id,
            KnowledgeSource.source_type == "legacy_memory",
            KnowledgeSource.source_ref == f"memory:{memory.id}",
        )
        .first()
    )
    assert source is not None
    claims = (
        db.query(KnowledgeClaim)
        .filter(KnowledgeClaim.user_id == user_id)
        .all()
    )
    assert len(claims) == 1
    assert claims[0].claim_text == legacy_content
    assert claims[0].metadata_json.get("legacy_memory_id") == memory.id

    # The legacy row is untouched and remains active.
    db.refresh(memory)
    assert memory.is_active is True
    assert memory.content == legacy_content

    second = migrate_memories_to_knowledge(db, user_id=user_id)
    assert second["migrated"] == 0
    assert second["already_migrated"] == 1
    assert db.query(KnowledgeClaim).count() == 1


def test_inactive_memories_are_ignored(db: Session, user_id: int):
    _memory(db, user_id, is_active=False)
    result = migrate_memories_to_knowledge(db, user_id=user_id)
    assert result["memories_considered"] == 0
    assert result["migrated"] == 0


def test_migrated_claims_are_searchable(db: Session, user_id: int):
    _memory(db, user_id)
    migrate_memories_to_knowledge(db, user_id=user_id)

    from app.knowledge.retrieval import knowledge_retrieval

    result = knowledge_retrieval.search(
        db, user_id=user_id, query="PostgreSQL", principal="user", limit=5
    )
    assert any("PostgreSQL" in item["claim_text"] for item in result["results"])
    # A migrated fact remains a fact with user-stated verification, not an inference.
    top = next(item for item in result["results"] if "PostgreSQL" in item["claim_text"])
    assert top["claim_type"] == "fact"
    assert top["verification_status"] == "user_stated"
