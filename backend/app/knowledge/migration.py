"""Non-destructive interoperability migration from ``ai_memories``.

The legacy memory subsystem remains fully operational. This module copies active
memories into the knowledge model, preserving source attribution and the
legacy memory id. It never updates or deletes ``ai_memories`` rows, so a
controlled rollout is reversible by simply stopping the migration.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.knowledge.service import knowledge_service
from app.knowledge.types import (
    ClaimType,
    NodeType,
    VerificationStatus,
    classify_sensitivity,
)
from app.models.ai_memory import AIMemory
from app.models.knowledge import KnowledgeClaim, KnowledgeSource

logger = get_logger("iris.knowledge.migration")

_CATEGORY_NODE_TYPE = {
    "PREFERENCE": NodeType.PREFERENCE.value,
    "PROJECT": NodeType.PROJECT.value,
    "CONSTRAINT": NodeType.CONCEPT.value,
    "INSTRUCTION": NodeType.PREFERENCE.value,
    "FACT": NodeType.TOPIC.value,
    "GENERAL": NodeType.TOPIC.value,
}

_CATEGORY_FOLDER = {
    "PREFERENCE": "personal",
    "PROJECT": "projects",
    "CONSTRAINT": "learning",
    "INSTRUCTION": "personal",
    "FACT": "learning",
    "GENERAL": "general",
}


def migrate_memories_to_knowledge(
    db: Session, *, user_id: int, dry_run: bool = False, limit: int = 500
) -> dict[str, Any]:
    memories = (
        db.query(AIMemory)
        .filter(AIMemory.user_id == user_id, AIMemory.is_active.is_(True))
        .order_by(AIMemory.importance.desc(), AIMemory.created_at.asc())
        .limit(max(1, min(limit, 2000)))
        .all()
    )
    migrated = 0
    skipped = 0
    failed = 0
    items: list[dict[str, Any]] = []
    for memory in memories:
        source_ref = f"memory:{memory.id}"
        existing = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.user_id == user_id,
                KnowledgeSource.source_type == "legacy_memory",
                KnowledgeSource.source_ref == source_ref,
            )
            .first()
        )
        if existing is not None:
            skipped += 1
            continue
        items.append(
            {
                "memory_id": memory.id,
                "category": memory.category,
                "key": memory.key,
                "content": memory.content[:2000],
                "importance": memory.importance,
                "confidence": memory.confidence,
                "source": memory.source,
            }
        )

    if dry_run:
        return {
            "dry_run": True,
            "memories_considered": len(memories),
            "would_migrate": len(items),
            "already_migrated": skipped,
            "items": items[:50],
        }

    for item in items:
        try:
            node_type = _CATEGORY_NODE_TYPE.get(str(item["category"]).upper(), NodeType.TOPIC.value)
            category = _CATEGORY_FOLDER.get(str(item["category"]).upper(), "general")
            node_name = item.get("key") or f"{str(item['category']).title()}: {item['content'][:60]}"
            sensitivity = classify_sensitivity(item["content"], node_type)
            source = knowledge_service.register_source(
                db,
                user_id=user_id,
                source_type="legacy_memory",
                source_ref=f"memory:{item['memory_id']}",
                title=(item.get("key") or item["content"][:80]),
                content=item["content"],
                metadata={
                    "legacy_memory_id": item["memory_id"],
                    "legacy_source": item["source"],
                    "migrated": True,
                },
                sensitivity=sensitivity,
            )
            node, _ = knowledge_service.resolve_node(
                db,
                user_id=user_id,
                name=node_name,
                node_type=node_type,
                sensitivity=sensitivity,
            )
            claim_type = (
                ClaimType.FACT.value
                if item["category"] in {"FACT", "PREFERENCE", "INSTRUCTION", "CONSTRAINT"}
                else ClaimType.OBSERVATION.value
            )
            knowledge_service.create_claim(
                db,
                user_id=user_id,
                node=node,
                text=item["content"],
                claim_type=claim_type,
                category=category,
                confidence=float(item.get("confidence") or 0.7),
                verification_status=VerificationStatus.USER_STATED.value,
                source_id=source.id,
                sensitivity=sensitivity,
                metadata={
                    "legacy_memory_id": item["memory_id"],
                    "legacy_category": item["category"],
                    "migrated": True,
                },
                extraction_method="legacy_migration",
                evidence_text=item["content"],
            )
            migrated += 1
        except Exception as exc:  # noqa: BLE001 - one bad memory must not stop the batch
            logger.warning(
                "knowledge_memory_migration_failed memory_id=%s error_type=%s",
                item.get("memory_id"),
                type(exc).__name__,
            )
            failed += 1

    db.commit()
    from sqlalchemy import func

    legacy_claims = (
        db.query(func.count(KnowledgeClaim.id))
        .filter(KnowledgeClaim.user_id == user_id)
        .scalar()
        or 0
    )
    logger.info(
        "knowledge_memory_migration_complete user_id=%s migrated=%s skipped=%s failed=%s",
        user_id,
        migrated,
        skipped,
        failed,
    )
    return {
        "dry_run": False,
        "memories_considered": len(memories),
        "migrated": migrated,
        "already_migrated": skipped,
        "failed": failed,
        "knowledge_records_present": legacy_claims,
        "legacy_memory_modified": False,
    }
