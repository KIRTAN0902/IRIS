"""Health + meta endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness + database check")
def health() -> dict:
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    from app.ai.health import ai_health

    ai_info = ai_health.get_status()

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "IRIS",
        "version": "0.1.0",
        "environment": settings.environment,
        "database": "ok" if db_ok else "unreachable",
        "ai": "enabled" if settings.ai_enabled else "deterministic-only",
        "ai_status": ai_info,
    }
