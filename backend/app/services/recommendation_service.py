"""Recommendation service.

Combines deterministic engines (priority, deadline, available time, constraints,
goals, startup metrics) with Gemini AI reasoning layer.
Delegates to the IRIS Decision Intelligence Layer.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.decision_engine import decide_now, deterministic_decision
from app.schemas.ai import RecommendationOut


def deterministic_recommendation(
    db: Session,
    user,
    *,
    available_minutes: int | None = None,
    window_start=None,
    window_end=None,
    current_energy: str | None = None,
) -> RecommendationOut:
    """Top-ranked decision computed deterministically."""
    result = deterministic_decision(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
        current_energy=current_energy,
    )
    return RecommendationOut.model_validate(result.model_dump(mode="json"))


async def ai_recommendation(
    db: Session,
    user,
    *,
    available_minutes: int | None = None,
    window_start=None,
    window_end=None,
    current_energy: str | None = None,
) -> tuple[RecommendationOut, str]:
    """AI-enhanced recommendation. Returns (recommendation, source).

    Falls back to deterministic recommendation whenever Gemini is unavailable
    or returns invalid output -- never raises to the caller.
    """
    result, source = await decide_now(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
        current_energy=current_energy,
    )
    rec_out = RecommendationOut.model_validate(result.model_dump(mode="json"))
    return rec_out, source
