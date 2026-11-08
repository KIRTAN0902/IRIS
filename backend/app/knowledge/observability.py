"""In-process knowledge metrics and health helpers.

Counters are intentionally lightweight and process-local. They are exposed by
``/api/knowledge/health`` and are safe to lose on restart; durable job state is
in ``knowledge_jobs``.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger("iris.knowledge.metrics")

_START = time.time()


class KnowledgeMetrics:
    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def observe(self, name: str, milliseconds: float) -> None:
        with self._lock:
            bucket = self._latencies[name]
            bucket.append(float(milliseconds))
            if len(bucket) > 500:
                del bucket[:250]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = {
                name: {
                    "count": len(values),
                    "avg_ms": round(sum(values) / len(values), 2) if values else None,
                    "max_ms": round(max(values), 2) if values else None,
                }
                for name, values in self._latencies.items()
            }
            return {
                "uptime_seconds": int(time.time() - _START),
                "counters": dict(self._counters),
                "latency": latencies,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._latencies.clear()


knowledge_metrics = KnowledgeMetrics()


def knowledge_health(db: Session) -> dict[str, Any]:
    """Aggregate operational health from real database state."""
    from app.models.knowledge import (
        KnowledgeClaim,
        KnowledgeEmbedding,
        KnowledgeJob,
        KnowledgeNode,
        KnowledgeNote,
        KnowledgeRelationship,
    )

    status_rows = (
        db.query(KnowledgeJob.status, func.count(KnowledgeJob.id))
        .group_by(KnowledgeJob.status)
        .all()
    )
    statuses = {status: count for status, count in status_rows}
    failed = statuses.get("failed", 0) + statuses.get("dead", 0)
    pending_notes = (
        db.query(func.count(KnowledgeNote.id))
        .filter(KnowledgeNote.sync_status.in_(["pending", "conflict", "failed"]))
        .scalar()
        or 0
    )
    counts = {
        "nodes": db.query(func.count(KnowledgeNode.id)).scalar() or 0,
        "claims": db.query(func.count(KnowledgeClaim.id)).scalar() or 0,
        "relationships": db.query(func.count(KnowledgeRelationship.id)).scalar() or 0,
        "notes": db.query(func.count(KnowledgeNote.id)).scalar() or 0,
        "embeddings": db.query(func.count(KnowledgeEmbedding.id)).scalar() or 0,
        "jobs": sum(statuses.values()),
    }
    if failed or pending_notes:
        state = "degraded"
    elif statuses.get("running"):
        state = "working"
    else:
        state = "healthy"
    return {
        "state": state,
        "counts": counts,
        "jobs_by_status": statuses,
        "queued_jobs": statuses.get("queued", 0),
        "failed_jobs": failed,
        "notes_requiring_sync": pending_notes,
        "metrics": knowledge_metrics.snapshot(),
    }
