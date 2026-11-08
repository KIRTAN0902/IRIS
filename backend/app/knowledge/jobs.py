"""Durable knowledge job queue.

No in-memory queue is used for correctness. Jobs are rows with a lease,
retry counter and dead-letter state, so a backend restart or interrupted
request cannot lose work or duplicate records.
"""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.knowledge.observability import knowledge_metrics
from app.knowledge.types import JobStatus, JobType, utcnow
from app.models.knowledge import KnowledgeJob

logger = get_logger("iris.knowledge.jobs")

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def enqueue_job(
    db: Session,
    *,
    user_id: int,
    job_type: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    priority: int = 100,
    max_attempts: int = 5,
    available_at=None,
) -> KnowledgeJob:
    key = (idempotency_key or f"{job_type}:{uuid4().hex}")[:200]
    existing = (
        db.query(KnowledgeJob)
        .filter(KnowledgeJob.user_id == user_id, KnowledgeJob.idempotency_key == key)
        .first()
    )
    if existing:
        return existing
    job = KnowledgeJob(
        user_id=user_id,
        job_type=job_type,
        status=JobStatus.QUEUED.value,
        priority=priority,
        payload=payload or {},
        idempotency_key=key,
        max_attempts=max_attempts,
        available_at=available_at or utcnow(),
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(KnowledgeJob)
            .filter(KnowledgeJob.user_id == user_id, KnowledgeJob.idempotency_key == key)
            .first()
        )
        if existing:
            return existing
        raise
    knowledge_metrics.increment("jobs_enqueued")
    return job


def recover_stale_jobs(db: Session) -> int:
    """Return expired leases to the queue; dead-letter exhausted jobs."""
    now = utcnow()
    stale = (
        db.query(KnowledgeJob)
        .filter(
            KnowledgeJob.status == JobStatus.RUNNING.value,
            KnowledgeJob.lease_expires_at.is_not(None),
            KnowledgeJob.lease_expires_at < now,
        )
        .limit(100)
        .all()
    )
    recovered = 0
    for job in stale:
        job.locked_at = None
        job.locked_by = None
        job.lease_expires_at = None
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.DEAD.value
            job.last_error = job.last_error or "Lease expired after maximum attempts."
            job.completed_at = now
        else:
            job.status = JobStatus.QUEUED.value
            job.available_at = now
            recovered += 1
    if stale:
        db.commit()
    return recovered


def claim_job(
    db: Session,
    worker_id: str = WORKER_ID,
    lease_seconds: int | None = None,
    *,
    user_id: int | None = None,
) -> KnowledgeJob | None:
    now = utcnow()
    lease = lease_seconds or settings.knowledge_job_lease_seconds
    query = (
        db.query(KnowledgeJob)
        .filter(
            KnowledgeJob.status == JobStatus.QUEUED.value,
            KnowledgeJob.available_at <= now,
        )
    )
    if user_id is not None:
        query = query.filter(KnowledgeJob.user_id == user_id)
    query = query.order_by(
        KnowledgeJob.priority.asc(),
        KnowledgeJob.available_at.asc(),
        KnowledgeJob.created_at.asc(),
    ).limit(1)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    job = query.first()
    if not job:
        db.rollback()
        return None
    job.status = JobStatus.RUNNING.value
    job.locked_at = now
    job.locked_by = worker_id
    job.lease_expires_at = now + timedelta(seconds=lease)
    job.attempts += 1
    db.commit()
    db.refresh(job)
    knowledge_metrics.increment("jobs_claimed")
    return job


def complete_job(db: Session, job: KnowledgeJob, result: dict[str, Any] | None = None) -> None:
    job.status = JobStatus.SUCCEEDED.value
    job.result = result or {}
    job.completed_at = utcnow()
    job.locked_at = None
    job.locked_by = None
    job.lease_expires_at = None
    job.last_error = None
    db.commit()
    knowledge_metrics.increment("jobs_succeeded")


def fail_job(db: Session, job: KnowledgeJob, error: str) -> None:
    now = utcnow()
    job.last_error = (error or "Unknown failure.")[:4000]
    job.locked_at = None
    job.locked_by = None
    job.lease_expires_at = None
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.DEAD.value
        job.completed_at = now
        knowledge_metrics.increment("jobs_dead")
    else:
        job.status = JobStatus.QUEUED.value
        delay = min(300, 5 * (2 ** max(0, job.attempts - 1)))
        job.available_at = now + timedelta(seconds=delay)
        knowledge_metrics.increment("jobs_retried")
    db.commit()


def process_job(db: Session, job: KnowledgeJob) -> dict[str, Any]:
    from app.knowledge.pipeline import process_extraction_job
    from app.knowledge.embeddings import embedding_service
    from app.knowledge.markdown_sync import markdown_sync
    from app.models.knowledge import KnowledgeClaim, KnowledgeNode

    payload = job.payload or {}
    if job.job_type == JobType.EXTRACT_KNOWLEDGE.value:
        return process_extraction_job(db, user_id=job.user_id, payload=payload)
    if job.job_type == JobType.GENERATE_EMBEDDINGS.value:
        knowledge_type = payload.get("knowledge_type")
        knowledge_id = payload.get("knowledge_id")
        if not knowledge_type or not knowledge_id:
            return {"skipped": "missing_reference"}
        if knowledge_type == "claim":
            claim = (
                db.query(KnowledgeClaim)
                .filter(KnowledgeClaim.id == knowledge_id, KnowledgeClaim.user_id == job.user_id)
                .first()
            )
            if not claim or claim.archived_at:
                return {"skipped": "claim_not_found"}
            embedding_service.upsert(
                db,
                user_id=job.user_id,
                knowledge_type="claim",
                knowledge_id=claim.id,
                text=claim.claim_text,
                content_version=1,
            )
            db.commit()
            return {"embedded": claim.id}
        if knowledge_type == "node":
            node = (
                db.query(KnowledgeNode)
                .filter(KnowledgeNode.id == knowledge_id, KnowledgeNode.user_id == job.user_id)
                .first()
            )
            if not node:
                return {"skipped": "node_not_found"}
            embedding_service.upsert(
                db,
                user_id=job.user_id,
                knowledge_type="node",
                knowledge_id=node.id,
                text=" ".join([node.canonical_name, node.description or ""]),
                content_version=1,
            )
            db.commit()
            return {"embedded": node.id}
        return {"skipped": "unsupported_knowledge_type"}
    if job.job_type == JobType.UPDATE_MARKDOWN.value:
        result = markdown_sync.sync_node(db, user_id=job.user_id, node_id=payload.get("node_id"))
        db.commit()
        return result
    if job.job_type == JobType.RECONCILE_VAULT.value:
        result = markdown_sync.reconcile(db, user_id=job.user_id)
        db.commit()
        return result
    if job.job_type == JobType.REBUILD_INDEXES.value:
        result = markdown_sync.rebuild_index(db, user_id=job.user_id)
        db.commit()
        return result
    if job.job_type == JobType.DETECT_CONTRADICTIONS.value:
        return {"checked": 0, "note": "Contradictions are detected synchronously at claim insertion."}
    if job.job_type in {JobType.RESOLVE_ENTITIES.value, JobType.CONSOLIDATE_KNOWLEDGE.value}:
        from app.knowledge.consolidation import consolidate_user_knowledge

        result = consolidate_user_knowledge(db, user_id=job.user_id, limit=int(payload.get("limit", 100)))
        db.commit()
        return result
    return {"skipped": f"unknown_job_type:{job.job_type}"}


def drain_jobs(
    db: Session,
    *,
    user_id: int | None = None,
    limit: int = 10,
    worker_id: str = WORKER_ID,
) -> dict[str, Any]:
    """Process a bounded number of jobs. Safe to call from a serverless request."""
    recover_stale_jobs(db)
    processed = 0
    failed = 0
    results: list[dict[str, Any]] = []
    for _ in range(max(1, min(limit, 50))):
        job = claim_job(db, worker_id=worker_id, user_id=user_id)
        if not job:
            break
        try:
            result = process_job(db, job)
            complete_job(db, job, result)
            results.append({"job_id": job.id, "job_type": job.job_type, "result": result})
            processed += 1
        except Exception as exc:  # noqa: BLE001 - job boundary
            db.rollback()
            job = (
                db.query(KnowledgeJob)
                .filter(KnowledgeJob.id == job.id)
                .first()
            )
            if job:
                fail_job(db, job, f"{type(exc).__name__}: {exc}")
            failed += 1
            logger.warning("knowledge_job_failed job_type=%s error_type=%s", job.job_type if job else "unknown", type(exc).__name__)
    return {"processed": processed, "failed": failed, "results": results}


async def worker_loop(stop: asyncio.Event) -> None:
    """Long-lived worker used by the FastAPI lifespan (never on serverless)."""
    logger.info("knowledge_worker_started worker_id=%s", WORKER_ID)
    while not stop.is_set():
        try:
            def _drain() -> dict[str, Any]:
                db = SessionLocal()
                try:
                    return drain_jobs(db, limit=settings.knowledge_worker_batch)
                finally:
                    db.close()

            # Lease, SQL and any synchronous provider bridge run off the event
            # loop so chat requests are never blocked by background work.
            result = await asyncio.to_thread(_drain)
            if result["processed"] == 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=settings.knowledge_worker_poll_seconds)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except Exception as exc:  # noqa: BLE001 - worker must survive
            logger.warning("knowledge_worker_error error_type=%s", type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.knowledge_worker_poll_seconds)
            except TimeoutError:
                pass
    logger.info("knowledge_worker_stopped worker_id=%s", WORKER_ID)


def job_stats(db: Session, *, user_id: int | None = None) -> dict[str, Any]:
    from sqlalchemy import func

    status_query = db.query(KnowledgeJob.status, func.count(KnowledgeJob.id))
    if user_id is not None:
        status_query = status_query.filter(KnowledgeJob.user_id == user_id)
    rows = status_query.group_by(KnowledgeJob.status).all()
    by_status = {status: count for status, count in rows}
    oldest_query = db.query(KnowledgeJob).filter(
        KnowledgeJob.status == JobStatus.QUEUED.value
    )
    if user_id is not None:
        oldest_query = oldest_query.filter(KnowledgeJob.user_id == user_id)
    oldest = oldest_query.order_by(KnowledgeJob.available_at.asc()).first()
    return {
        "by_status": by_status,
        "queued": by_status.get(JobStatus.QUEUED.value, 0),
        "running": by_status.get(JobStatus.RUNNING.value, 0),
        "failed": by_status.get(JobStatus.FAILED.value, 0),
        "dead": by_status.get(JobStatus.DEAD.value, 0),
        "oldest_queued_at": oldest.available_at.isoformat() if oldest else None,
        "worker_id": WORKER_ID,
    }
