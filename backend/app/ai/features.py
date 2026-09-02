"""AI feature modules -- thin orchestration around generic AIProvider.

Every function takes a deterministic fallback; on ANY AI failure it returns
the fallback instead of raising, so AI outages never break the API
(spec §46). Returns (result, source) where source is "AI" | "DETERMINISTIC".
"""

from __future__ import annotations

from datetime import datetime

from app.ai.factory import get_ai_provider
from app.ai.prompts import DAILY_REVIEW, PLANNER, RECOMMENDER, STARTUP_ANALYSIS, with_context
from app.ai.provider import AIProviderError
from app.core.logging import get_logger
from app.schemas.ai import (
    DailyReviewOut,
    PlanDayOut,
    RecommendationOut,
    StartupAnalysisOut,
)

logger = get_logger("iris.ai.features")

Source = str  # "AI" | "DETERMINISTIC"


def _context_ids(context: dict) -> set[int]:
    return {t["task"]["id"] for t in context.get("ranked_tasks", [])}


async def generate_recommendation(
    context: dict, *, fallback: RecommendationOut
) -> tuple[RecommendationOut, Source]:
    provider = get_ai_provider()
    if not provider.enabled:
        return fallback, "DETERMINISTIC"
    try:
        result = await provider.generate_structured(
            system=with_context(RECOMMENDER, context),
            prompt="Recommend what I should do right now.",
            schema=RecommendationOut,
        )
        # Guardrail 1: TASK recommendations must reference a task from the context.
        if result.recommendation_type == "TASK":
            if result.task_id is None or result.task_id not in _context_ids(context):
                logger.info(
                    "AI task_id %s not in context; using deterministic fallback", result.task_id
                )
                return fallback, "DETERMINISTIC"

        # Guardrail 2: Hard constraint clamp (cannot exceed available minutes)
        avail = context.get("available_minutes")
        if avail and result.duration_minutes and result.duration_minutes > avail:
            result.duration_minutes = avail

        return result, "AI"
    except (AIProviderError, Exception) as exc:  # AI must never break the API (spec 41)
        logger.warning("Recommendation fallback: %s: %s", type(exc).__name__, exc)
        return fallback, "DETERMINISTIC"


async def generate_plan_day(
    context: dict, *, deterministic: PlanDayOut
) -> tuple[PlanDayOut, Source]:
    provider = get_ai_provider()
    if not provider.enabled:
        return deterministic, "DETERMINISTIC"
    try:
        result = await provider.generate_structured(
            system=with_context(PLANNER, context),
            prompt="Plan my day according to the rules and free intervals.",
            schema=PlanDayOut,
        )
        # Guardrails: task references must exist; blocks must sit inside free windows.
        valid_ids = _context_ids(context)
        allowed = [(i["start"], i["end"]) for i in context.get("free_intervals_utc", [])]
        clean = []
        for b in result.blocks:
            if b.task_id is not None and b.task_id not in valid_ids:
                b.task_id = None
            if allowed and not _within_any(b.start, b.end, allowed):
                continue
            clean.append(b)
        dropped_ids = {b.task_id for b in result.blocks} - {b.task_id for b in clean}
        result.blocks = clean
        result.unscheduled_task_ids = sorted(
            set(result.unscheduled_task_ids)
            | {i for i in dropped_ids if i is not None}
            | (set(deterministic.unscheduled_task_ids) - {b.task_id for b in clean})
        )
        return result, "AI"
    except (AIProviderError, Exception) as exc:  # AI must never break the API (spec 41)
        logger.warning("Plan-day fallback: %s: %s", type(exc).__name__, exc)
        return deterministic, "DETERMINISTIC"


def _within_any(start: datetime, end: datetime, intervals: list[tuple[str, str]]) -> bool:
    s, e = start.isoformat(), end.isoformat()
    return any(s >= a and e <= b for a, b in intervals)


async def generate_daily_review(
    context: dict, *, fallback_summary: str
) -> tuple[DailyReviewOut, Source]:
    deterministic = DailyReviewOut(summary=fallback_summary)
    provider = get_ai_provider()
    if not provider.enabled:
        return deterministic, "DETERMINISTIC"
    try:
        result = await provider.generate_structured(
            system=with_context(DAILY_REVIEW, context),
            prompt="Write my daily review based on this data.",
            schema=DailyReviewOut,
        )
        return result, "AI"
    except (AIProviderError, Exception) as exc:  # AI must never break the API (spec 41)
        logger.warning("Daily review fallback: %s: %s", type(exc).__name__, exc)
        return deterministic, "DETERMINISTIC"


async def generate_startup_analysis(
    context: dict, *, fallback: StartupAnalysisOut
) -> tuple[StartupAnalysisOut, Source]:
    provider = get_ai_provider()
    if not provider.enabled:
        return fallback, "DETERMINISTIC"
    try:
        result = await provider.generate_structured(
            system=with_context(STARTUP_ANALYSIS, context),
            prompt="Analyze my startup's progress from this data.",
            schema=StartupAnalysisOut,
        )
        return result, "AI"
    except (AIProviderError, Exception) as exc:  # AI must never break the API (spec 41)
        logger.warning("Startup analysis fallback: %s: %s", type(exc).__name__, exc)
        return fallback, "DETERMINISTIC"
