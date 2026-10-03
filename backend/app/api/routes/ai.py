"""AI endpoints. All AI failures degrade to deterministic fallbacks."""

from __future__ import annotations

from datetime import UTC, date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai import features
from app.api.deps import current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.enums import AIRole
from app.models.user import User
from app.schemas.ai import (
    DailyReviewResponse,
    PlanDayOut,
    PlanDayResponse,
    RecommendationResponse,
    StartupAnalysisOut,
    StartupAnalysisResponse,
)
from app.services import context_builder, recommendation_service, time_engine
from app.utils.datetime import localize_date_boundaries, utcnow

router = APIRouter(prefix="/ai", tags=["ai"])


def _ai_meta(source: str) -> dict:
    return {
        "source": source,
        "ai_available": settings.ai_enabled and source == "AI",
    }


class AskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    conversation_id: int | None = None


@router.post("/recommend", response_model=RecommendationResponse, summary="What should I do now?")
async def recommend(
    available_minutes: int | None = Query(None, ge=1, le=24 * 60),
    window_start=None,
    window_end=None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    result, source = await recommendation_service.ai_recommendation(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
    )
    payload = result.model_dump(mode="json")
    payload.update(_ai_meta(source))
    return payload


@router.post(
    "/plan-day", response_model=PlanDayResponse, summary="Draft a day plan (not persisted)"
)
async def plan_day(
    plan_date: date = Query(default_factory=date.today),
    available_start=None,
    available_end=None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Returns a DRAFT plan. Nothing is written until the client confirms via
    POST /api/time-blocks for each accepted block."""
    from datetime import datetime as dt

    if available_start and isinstance(available_start, str):
        available_start = dt.fromisoformat(available_start)
    if available_end and isinstance(available_end, str):
        available_end = dt.fromisoformat(available_end)

    day_start_utc, day_end_utc = localize_date_boundaries(plan_date, user.timezone)
    now = utcnow()
    start = available_start or (
        max(day_start_utc, now) if plan_date == now.date() else day_start_utc
    )
    end = available_end or day_end_utc

    avail = time_engine.compute_availability(db, user.id, window_start=start, window_end=end)

    # Deterministic greedy fill of free intervals by priority rank.
    from app.services.context_builder import build_recommendation_context

    context = build_recommendation_context(
        db,
        user,
        available_minutes=avail.total_free_minutes,
        window_start=start,
        window_end=end,
    )
    ranked = context["ranked_tasks"]
    blocks: list[dict] = []
    scheduled_ids: set[int] = set()
    unscheduled: list[int] = []

    queue = [dict(item) for item in ranked]
    intervals = [dict(i) for i in context["free_intervals_utc"]]
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    parsed_intervals = [
        {"start": _dt.fromisoformat(i["start"]), "end": _dt.fromisoformat(i["end"])}
        for i in intervals
    ]

    for item in queue:
        task = item["task"]
        est = task.get("estimated_duration") or 45
        placed = False
        for interval in parsed_intervals:
            gap = int((interval["end"] - interval["start"]).total_seconds() // 60)
            if gap <= 0:
                continue
            chunk = min(est, gap)
            block_start: _dt = interval["start"]
            block_end = block_start + _td(minutes=chunk)
            notes = item["breakdown"].get("notes") or []
            blocks.append(
                {
                    "task_id": task["id"],
                    "start": block_start.isoformat(),
                    "end": block_end.isoformat(),
                    "reason": notes[0] if notes else f"priority {item['priority_score']}",
                }
            )
            est -= chunk
            interval["start"] = block_end
            if est <= 0:
                scheduled_ids.add(task["id"])
                placed = True
                break
        if not placed:
            unscheduled.append(task["id"])

    deterministic_plan = PlanDayOut(
        date=plan_date,
        blocks=blocks,
        unscheduled_task_ids=unscheduled,
        summary=None,
    )

    result, source = await features.generate_plan_day(context, deterministic=deterministic_plan)
    payload = result.model_dump(mode="json")
    payload.update(_ai_meta(source))
    return payload


@router.post("/daily-review", response_model=DailyReviewResponse, summary="AI end-of-day review")
async def daily_review(
    review_date: date | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from zoneinfo import ZoneInfo

    today_local = utcnow().replace(tzinfo=UTC).astimezone(ZoneInfo(user.timezone)).date()
    target_date = review_date or today_local

    context = context_builder.build_daily_review_context(db, user, local_date=target_date)

    completed_n = len(context["completed_tasks"])
    missed_n = len(context["missed_or_overdue_tasks"])
    minutes_by_area = context["time_by_area_minutes"]
    fallback_summary = (
        (
            f"{target_date.isoformat()}: {completed_n} task(s) completed, "
            f"{missed_n} overdue/open with deadlines. Focus minutes â€” "
            + ", ".join(f"{a}: {int(m)}" for a, m in minutes_by_area.items() if m > 0)
            + "."
        )
        if (completed_n or missed_n)
        else (f"{target_date.isoformat()}: no recorded completions or focus sessions.")
    )

    result, source = await features.generate_daily_review(
        context, fallback_summary=fallback_summary
    )
    payload = result.model_dump(mode="json")
    payload.update(_ai_meta(source))
    return payload


@router.post("/startup-analysis", response_model=StartupAnalysisResponse)
async def startup_analysis(
    startup_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    context = context_builder.build_startup_analysis_context(db, user, startup_id=startup_id)

    metrics = context.get("metrics", {})
    outreach = metrics.get("outreach", {})
    fallback = StartupAnalysisOut(
        observation=(
            f"Total outreach: {outreach.get('total', 0)}, "
            f"reply rate {outreach.get('reply_rate', 0)}%, "
            f"meeting rate {outreach.get('meeting_rate', 0)}%, "
            f"conversions {outreach.get('conversions', 0)}."
        ),
        possible_cause=None,
        recommendation=(
            "Log more outreach activities to gather statistically meaningful data."
            if (outreach.get("total", 0) < 20)
            else None
        ),
        priority="MEDIUM" if outreach.get("total", 0) else "LOW",
        data_evidence={
            k: float(v)
            for k, v in {
                "total_outreach": outreach.get("total", 0),
                "reply_rate_pct": outreach.get("reply_rate", 0),
                "meeting_rate_pct": outreach.get("meeting_rate", 0),
                "customers": outreach.get("conversions", 0),
            }.items()
        },
    )

    result, source = await features.generate_startup_analysis(context, fallback=fallback)
    payload = result.model_dump(mode="json")
    payload.update(_ai_meta(source))
    return payload


# --- Ask IRIS (conversation) ---------------------------------------------------


@router.post("/ask", summary="Ask IRIS anything about your life data")
async def ask_iris(
    data: AskIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.ai.factory import get_ai_provider
    from app.ai.prompts import IDENTITY, with_context

    provider = get_ai_provider()

    # Resolve/create conversation.
    conversation = None
    if data.conversation_id:
        conversation = (
            db.query(AIConversation)
            .filter(AIConversation.id == data.conversation_id, AIConversation.user_id == user.id)
            .first()
        )
    if conversation is None:
        conversation = AIConversation(user_id=user.id, title=data.question[:120])
        db.add(conversation)
        db.flush()

    history = conversation.messages[-8:]
    context = context_builder.build_ask_context(db, user, question=data.question)

    answer_text: str | None = None
    source = "DETERMINISTIC"
    if provider.enabled:
        try:
            transcript = "\n".join(f"{m.role}: {m.content}" for m in history)
            prompt = (
                f"Recent conversation:\n{transcript}\n\n" if transcript else ""
            ) + "Answer the user's question."

            class _Answer(BaseModel):
                answer: str
                follow_ups: list[str] = []

            result = await provider.generate_structured(
                system=with_context(IDENTITY, context), prompt=prompt, schema=_Answer
            )
            answer_text = result.answer
            source = "AI"
        except Exception as exc:  # AI must never break the API (spec 41)
            from app.core.logging import get_logger

            get_logger("iris.ai").warning("Ask fallback: %s: %s", type(exc).__name__, exc)

    if answer_text is None:
        # Deterministic fallback: a factual digest instead of generic advice.
        deadlines = context["upcoming_deadlines"]
        wp = context["week_productivity"]
        sm = context.get("startup_metrics")
        lines = ["Here is what your data says right now:"]
        if deadlines[:5]:
            lines.append(
                "Upcoming deadlines: "
                + "; ".join(
                    f"{d['title']} ({d['area']}, {d['minutes_until_deadline']}m left)"
                    for d in deadlines[:5]
                )
            )
        lines.append(
            f"This week: {wp['tasks_completed']} tasks completed, "
            f"{wp['focus_minutes']:.0f} focus minutes, completion rate {wp['completion_rate']}%."
        )
        if sm:
            lines.append(
                f"Startup: {sm['pipeline']['leads_total']} leads, "
                f"{sm['outreach']['total']} outreach, "
                f"{sm['outreach']['reply_rate']}% reply rate."
            )
        answer_text = "\n".join(lines)

    # Persist the exchange.
    db.add(
        AIMessage(conversation_id=conversation.id, role=AIRole.USER.value, content=data.question)
    )
    db.add(
        AIMessage(conversation_id=conversation.id, role=AIRole.ASSISTANT.value, content=answer_text)
    )
    conversation.title = conversation.title or data.question[:120]
    db.commit()

    from app.services.memory_service import memory_service

    await memory_service.extract_and_store_from_conversation(
        db=db,
        user=user,
        user_message=data.question,
        assistant_message=answer_text,
        conversation_id=conversation.id,
    )


    return {
        "answer": answer_text,
        "follow_ups": [],
        "conversation_id": conversation.id,
        **_ai_meta(source),
    }


@router.get("/conversations")
def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AIConversation)
        .filter(AIConversation.user_id == user.id)
        .order_by(AIConversation.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at} for c in rows]


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException

    conversation = (
        db.query(AIConversation)
        .filter(AIConversation.id == conversation_id, AIConversation.user_id == user.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
        for m in conversation.messages
    ]


@router.get("/status", summary="AI provider health and connectivity status")
def ai_status() -> dict[str, Any]:
    """Return live status of the active AI provider (OPERATIONAL, NOT_RESPONDING, NOT_CONFIGURED)."""
    from app.ai.health import ai_health

    return ai_health.get_status()
