"""Knowledge processing pipeline: source -> extraction -> persistence -> jobs."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.knowledge.extraction import (
    ExtractionResult,
    heuristic_extract,
    is_trivial,
    llm_extract,
)
from app.knowledge.jobs import enqueue_job
from app.knowledge.service import knowledge_service
from app.knowledge.types import JobType
from app.models.knowledge import KnowledgeSource

logger = get_logger("iris.knowledge.pipeline")


def _run_coroutine(coro):
    """Run an async provider call from sync worker code, including inside a loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


def extract_text(text: str, *, origin: str) -> ExtractionResult:
    from app.ai.factory import get_ai_provider

    provider = get_ai_provider()
    if provider.enabled:
        try:
            result = _run_coroutine(llm_extract(text, origin=origin))
            if result.items or result.skipped_reason:
                return result
        except Exception as exc:  # noqa: BLE001
            logger.info("knowledge_extraction_llm_failed error_type=%s", type(exc).__name__)
    return heuristic_extract(text, origin=origin)


def capture_conversation_turn(
    db: Session,
    *,
    user_id: int,
    user_message: str,
    assistant_message: str = "",
    conversation_id: int | None = None,
    message_id: int | None = None,
) -> dict[str, Any] | None:
    """Register provenance and enqueue extraction. Never blocks the chat reply."""
    if not settings.knowledge_capture_enabled:
        return None
    text = (user_message or "").strip()
    if not text or is_trivial(text):
        return None
    source_ref = (
        f"conversation:{conversation_id}:message:{message_id}"
        if conversation_id and message_id
        else f"conversation:{conversation_id}:{hash(text) & 0xFFFFFFFF:x}"
    )
    source = knowledge_service.register_source(
        db,
        user_id=user_id,
        source_type="conversation",
        source_ref=source_ref,
        title=(text[:80] or "Conversation turn"),
        content=text,
        conversation_id=conversation_id,
        message_id=message_id,
        metadata={"assistant_excerpt": (assistant_message or "")[:500]},
    )
    job = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.EXTRACT_KNOWLEDGE.value,
        payload={
            "source_id": source.id,
            "text": text,
            "assistant_text": (assistant_message or "")[:4000],
            "origin": "conversation",
        },
        idempotency_key=f"extract:{source.id}",
        priority=50,
    )
    db.commit()
    return {"source_id": source.id, "job_id": job.id}


def capture_text(
    db: Session,
    *,
    user_id: int,
    text: str,
    source_type: str = "user_provided",
    source_ref: str | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
    origin: str = "user",
    process_now: bool = False,
) -> dict[str, Any]:
    """Capture durable information from a document, coworker summary or note."""
    source = knowledge_service.register_source(
        db,
        user_id=user_id,
        source_type=source_type,
        source_ref=source_ref or f"{source_type}:{abs(hash(text)) & 0xFFFFFFFF:x}",
        title=title,
        content=text,
        metadata=metadata or {},
    )
    job = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.EXTRACT_KNOWLEDGE.value,
        payload={
            "source_id": source.id,
            "text": text,
            "origin": origin,
        },
        idempotency_key=f"extract:{source.id}",
        priority=40 if source_type in {"decision", "coworker_summary"} else 100,
    )
    db.commit()
    if process_now:
        from app.knowledge.jobs import drain_jobs

        drain_jobs(db, user_id=user_id, limit=1)
    return {"source_id": source.id, "job_id": job.id}


def process_extraction_job(db: Session, *, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == payload.get("source_id"),
            KnowledgeSource.user_id == user_id,
        )
        .first()
    )
    text = (payload.get("text") or "").strip()
    if source is None or not text:
        return {"skipped": "source_or_text_missing"}
    origin = payload.get("origin") or "conversation"
    result = extract_text(text, origin=origin)
    if not result.items:
        return {
            "created_claims": 0,
            "excluded": result.excluded,
            "skipped_reason": result.skipped_reason or "no_durable_items",
            "method": result.method,
        }
    summary = knowledge_service.persist_extraction(
        db, user_id=user_id, source=source, items=result.items
    )
    summary.update(
        {
            "method": result.method,
            "excluded": result.excluded,
            "extracted": len(result.items),
        }
    )
    db.commit()
    logger.info(
        "knowledge_extracted user_id=%s claims=%s duplicates=%s nodes=%s",
        user_id,
        summary["created_claims"],
        summary["duplicate_claims"],
        summary["created_nodes"],
    )
    return summary


def capture_coworker_result(
    db: Session,
    *,
    user_id: int,
    coworker_name: str,
    task_id: str,
    instruction: str,
    output: str,
) -> dict[str, Any] | None:
    """Coworker project summaries/decisions are first-class capture sources."""
    if not settings.knowledge_capture_enabled or not output.strip():
        return None
    text = f"Task: {instruction}\n\nResult: {output}"
    return capture_text(
        db,
        user_id=user_id,
        text=text[:12000],
        source_type="coworker_summary",
        source_ref=f"coworker:{coworker_name}:task:{task_id}",
        title=f"{coworker_name} task result",
        metadata={"coworker": coworker_name, "task_id": task_id},
        origin="coworker",
    )
