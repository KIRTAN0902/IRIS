from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.knowledge.jobs import (
    claim_job,
    complete_job,
    drain_jobs,
    enqueue_job,
    fail_job,
    job_stats,
    recover_stale_jobs,
)
from app.knowledge.service import knowledge_service
from app.knowledge.types import JobStatus, JobType, utcnow
from app.models.knowledge import KnowledgeEmbedding, KnowledgeJob


def test_enqueue_is_idempotent(db: Session, user_id: int):
    first = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.GENERATE_EMBEDDINGS.value,
        payload={"knowledge_type": "node", "knowledge_id": "abc"},
        idempotency_key="embed:abc",
    )
    db.commit()
    second = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.GENERATE_EMBEDDINGS.value,
        payload={"knowledge_type": "node", "knowledge_id": "abc"},
        idempotency_key="embed:abc",
    )
    db.commit()
    assert first.id == second.id
    assert db.query(KnowledgeJob).filter(KnowledgeJob.user_id == user_id).count() == 1


def test_claim_lease_and_stale_recovery(db: Session, user_id: int):
    job = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.UPDATE_MARKDOWN.value,
        payload={"node_id": "node-1"},
        idempotency_key="markdown:node-1",
    )
    db.commit()

    claimed = claim_job(db, user_id=user_id, worker_id="test-worker", lease_seconds=30)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING.value
    assert claimed.attempts == 1
    assert claimed.locked_by == "test-worker"
    assert claimed.lease_expires_at is not None

    # A live lease must not be stolen.
    assert claim_job(db, user_id=user_id, worker_id="other-worker") is None

    claimed.lease_expires_at = utcnow() - timedelta(seconds=5)
    db.commit()
    recovered = recover_stale_jobs(db)
    assert recovered == 1
    db.refresh(claimed)
    assert claimed.status == JobStatus.QUEUED.value
    assert claimed.locked_by is None
    assert claimed.lease_expires_at is None


def test_exhausted_lease_is_dead_lettered(db: Session, user_id: int):
    job = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.UPDATE_MARKDOWN.value,
        payload={},
        idempotency_key="markdown:dead",
        max_attempts=1,
    )
    db.commit()
    claimed = claim_job(db, user_id=user_id, worker_id="test-worker")
    assert claimed is not None
    claimed.lease_expires_at = utcnow() - timedelta(seconds=5)
    db.commit()

    recover_stale_jobs(db)
    db.refresh(job)
    assert job.status == JobStatus.DEAD.value
    assert job.last_error


def test_fail_job_backs_off_then_dead_letters(db: Session, user_id: int):
    job = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.UPDATE_MARKDOWN.value,
        payload={},
        idempotency_key="markdown:retry",
        max_attempts=2,
    )
    db.commit()

    first = claim_job(db, user_id=user_id, worker_id="test-worker")
    assert first is not None
    fail_job(db, first, "boom")
    db.refresh(first)
    assert first.status == JobStatus.QUEUED.value
    assert first.last_error == "boom"
    assert first.available_at > utcnow() - timedelta(seconds=1)

    # The retry is not immediately available because of the backoff delay.
    assert claim_job(db, user_id=user_id, worker_id="test-worker") is None

    first.available_at = utcnow() - timedelta(seconds=1)
    db.commit()
    second = claim_job(db, user_id=user_id, worker_id="test-worker")
    assert second is not None
    fail_job(db, second, "boom again")
    db.refresh(job)
    assert job.status == JobStatus.DEAD.value
    assert job.completed_at is not None


def test_drain_processes_embedding_job(db: Session, user_id: int):
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="Drain Target", node_type="topic"
    )
    claim, _ = knowledge_service.create_claim(
        db, user_id=user_id, node=node, text="The drain target exists."
    )
    enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.GENERATE_EMBEDDINGS.value,
        payload={"knowledge_type": "claim", "knowledge_id": claim.id},
        idempotency_key=f"embed:claim:{claim.id}",
    )
    db.commit()

    result = drain_jobs(db, user_id=user_id, limit=5, worker_id="test-worker")
    assert result["processed"] == 1
    assert result["failed"] == 0

    embedding = (
        db.query(KnowledgeEmbedding)
        .filter(
            KnowledgeEmbedding.user_id == user_id,
            KnowledgeEmbedding.knowledge_type == "claim",
            KnowledgeEmbedding.knowledge_id == claim.id,
        )
        .first()
    )
    assert embedding is not None
    assert embedding.dimensions >= 32


def test_job_stats_are_user_scoped(db: Session, user_id: int):
    enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.UPDATE_MARKDOWN.value,
        payload={},
        idempotency_key="stats:mine",
    )
    db.commit()
    stats = job_stats(db, user_id=user_id)
    assert stats["queued"] == 1
    assert stats["by_status"][JobStatus.QUEUED.value] == 1

    other = job_stats(db, user_id=user_id + 9999)
    assert other["queued"] == 0
