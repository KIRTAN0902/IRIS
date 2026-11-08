"""Bounded knowledge consolidation and embedding repair.

Consolidation is deliberately conservative. Exact duplicates are merged because
they are provably the same assertion. Near duplicates are *reported* for review,
never silently merged, and historical claims are never deleted. All work is
bounded so a background job cannot scan an unbounded knowledge base.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.knowledge import resolution
from app.knowledge.jobs import enqueue_job
from app.knowledge.types import JobType
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEmbedding,
    KnowledgeEvidence,
    KnowledgeReview,
    KnowledgeVersion,
)

logger = get_logger("iris.knowledge.consolidation")


def _review_exists(db: Session, user_id: int, target_id: str, review_type: str) -> bool:
    return (
        db.query(KnowledgeReview.id)
        .filter(
            KnowledgeReview.user_id == user_id,
            KnowledgeReview.target_type == "claim",
            KnowledgeReview.target_id == target_id,
            KnowledgeReview.review_type == review_type,
            KnowledgeReview.status == "open",
        )
        .first()
        is not None
    )


def consolidate_user_knowledge(
    db: Session, *, user_id: int, limit: int = 100
) -> dict[str, Any]:
    """Merge exact duplicate claims and report probable duplicates.

    ``limit`` bounds the number of active claims considered in one run.
    """
    limit = max(10, min(int(limit), 400))
    claims = (
        db.query(KnowledgeClaim)
        .filter(KnowledgeClaim.user_id == user_id, KnowledgeClaim.archived_at.is_(None))
        .order_by(KnowledgeClaim.node_id.asc(), KnowledgeClaim.recorded_at.asc())
        .limit(limit)
        .all()
    )

    by_node: dict[str, list[KnowledgeClaim]] = defaultdict(list)
    for claim in claims:
        by_node[claim.node_id].append(claim)

    merged = 0
    reported = 0
    merged_ids: set[str] = set()
    for node_claims in by_node.values():
        by_fingerprint: dict[str, list[KnowledgeClaim]] = defaultdict(list)
        for claim in node_claims:
            by_fingerprint[claim.fingerprint].append(claim)
        for duplicates in by_fingerprint.values():
            if len(duplicates) < 2:
                continue
            keeper = duplicates[0]
            for duplicate in duplicates[1:]:
                merged_ids.add(duplicate.id)
                db.query(KnowledgeEvidence).filter(
                    KnowledgeEvidence.user_id == user_id,
                    KnowledgeEvidence.claim_id == duplicate.id,
                ).update({"claim_id": keeper.id}, synchronize_session=False)
                latest = (
                    db.query(func.max(KnowledgeVersion.version_number))
                    .filter(
                        KnowledgeVersion.user_id == user_id,
                        KnowledgeVersion.entity_type == "claim",
                        KnowledgeVersion.entity_id == keeper.id,
                    )
                    .scalar()
                )
                db.add(
                    KnowledgeVersion(
                        user_id=user_id,
                        entity_type="claim",
                        entity_id=keeper.id,
                        version_number=int(latest or 0) + 1,
                        change_type="merge",
                        change_reason="exact_duplicate",
                        actor="iris",
                        snapshot={"merged_claim_id": duplicate.id},
                    )
                )
                db.delete(duplicate)
                merged += 1

        # Report, never merge, near duplicates with a different fingerprint.
        for index, left in enumerate(node_claims):
            if left.id in merged_ids:
                continue
            for right in node_claims[index + 1 :]:
                if right.id in merged_ids:
                    continue
                if left.fingerprint == right.fingerprint:
                    continue
                if left.claim_type != right.claim_type:
                    continue
                if not resolution.is_near_duplicate(left.claim_text, right.claim_text, threshold=0.88):
                    continue
                if _review_exists(db, user_id, left.id, "possible_duplicate"):
                    continue
                db.add(
                    KnowledgeReview(
                        user_id=user_id,
                        review_type="possible_duplicate",
                        target_type="claim",
                        target_id=left.id,
                        status="open",
                        reason="Two claims are textually similar but not provably identical.",
                        details={"other_claim_id": right.id, "similarity_band": "high"},
                    )
                )
                reported += 1
                if reported >= 25:
                    break
            if reported >= 25:
                break
        if reported >= 25:
            break

    enqueued = enqueue_missing_embeddings(db, user_id=user_id, limit=min(limit, 100))
    db.flush()
    logger.info(
        "knowledge_consolidated user_id=%s merged=%s reported=%s embeddings=%s",
        user_id,
        merged,
        reported,
        enqueued,
    )
    return {
        "claims_considered": len(claims),
        "merged_exact_duplicates": merged,
        "reported_possible_duplicates": reported,
        "embedding_jobs": enqueued,
    }


def enqueue_missing_embeddings(
    db: Session, *, user_id: int, limit: int = 100, model: str | None = None
) -> int:
    from app.knowledge.embeddings import get_embedding_provider

    model_name = model or get_embedding_provider().name
    embedded_ids = (
        db.query(KnowledgeEmbedding.knowledge_id)
        .filter(
            KnowledgeEmbedding.user_id == user_id,
            KnowledgeEmbedding.knowledge_type == "claim",
            KnowledgeEmbedding.model == model_name,
        )
        .subquery()
    )
    missing = (
        db.query(KnowledgeClaim)
        .filter(
            KnowledgeClaim.user_id == user_id,
            KnowledgeClaim.archived_at.is_(None),
            ~KnowledgeClaim.id.in_(embedded_ids),
        )
        .order_by(KnowledgeClaim.recorded_at.desc())
        .limit(max(1, min(limit, 250)))
        .all()
    )
    for claim in missing:
        enqueue_job(
            db,
            user_id=user_id,
            job_type=JobType.GENERATE_EMBEDDINGS.value,
            payload={"knowledge_type": "claim", "knowledge_id": claim.id},
            idempotency_key=f"embed:claim:{claim.id}",
            priority=70,
        )
    return len(missing)
