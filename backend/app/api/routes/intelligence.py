"""Intelligence & Today state API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.intelligence.attention_engine import generate_attention_items
from app.intelligence.context import build_decision_context
from app.intelligence.decision_engine import decide_now, deterministic_decision
from app.intelligence.recommendation import DecisionRecommendationOut
from app.intelligence.signals import SignalQuery, signal_repo
from app.models.ai_recommendation import AIRecommendation
from app.models.enums import DecisionFeedbackStatus
from app.models.recurring_schedule import RecurringSchedule
from app.models.user import User
from app.schemas.intelligence import (
    AttentionItemOut,
    CurrentWindowInfo,
    DecisionFeedbackIn,
    DecisionFeedbackOut,
    DecisionHistoryOut,
    RecurringScheduleIn,
    RecurringScheduleOut,
    RecurringScheduleUpdate,
    SignalOut,
    TodayStateOut,
)
from app.utils.datetime import utcnow

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


@router.get("/today", response_model=TodayStateOut)
def get_today_state(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Return a coherent current-state snapshot of today's schedule, flexible windows,
    urgent obligations, open tasks, active goals, startup bottleneck, attention items,
    domain signals, and recommendation.
    """
    context = build_decision_context(db, user)
    rec = deterministic_decision(db, user)

    # Compute total flexible minutes for today from flexible_windows or availability
    flexible_windows = context.get("flexible_windows", [])
    total_flex = 0
    for w in flexible_windows:
        try:
            s_h, s_m = map(int, w["start"].split(":"))
            e_h, e_m = map(int, w["end"].split(":"))
            total_flex += (e_h * 60 + e_m) - (s_h * 60 + s_m)
        except Exception:
            pass

    if total_flex == 0:
        total_flex = context.get("available_minutes", 120)

    cur_win = context.get("current_window", {})
    current_window_info = CurrentWindowInfo(
        is_in_flexible_window=cur_win.get("is_in_flexible_window", False),
        is_in_hard_constraint=cur_win.get("is_in_hard_constraint", False),
        active_block_name=cur_win.get("active_block_name"),
        active_block_type=cur_win.get("active_block_type"),
        minutes_remaining_in_block=cur_win.get("minutes_remaining_in_block"),
        minutes_until_next_hard_constraint=cur_win.get("minutes_until_next_hard_constraint"),
        next_hard_constraint_name=cur_win.get("next_hard_constraint_name"),
    )

    rec_summary = {
        "recommendation_type": rec.recommendation_type,
        "decision_type": rec.decision_type,
        "decision": rec.decision,
        "task_id": rec.task_id,
        "title": rec.title,
        "reason": rec.reason,
        "duration_minutes": rec.duration_minutes,
        "expected_outcome": rec.expected_outcome,
        "confidence": rec.confidence,
        "opportunity_cost": rec.opportunity_cost,
        "evidence": rec.evidence,
    }

    local_iso = context["current_local_time"]
    date_str = local_iso.split("T")[0]
    time_str = local_iso.split("T")[1][:5] if "T" in local_iso else local_iso

    # Fetch recent decisions for today
    recent_recs = (
        db.query(AIRecommendation)
        .filter(AIRecommendation.user_id == user.id)
        .order_by(AIRecommendation.created_at.desc())
        .limit(5)
        .all()
    )
    recent_list = [
        {
            "id": r.id,
            "title": r.title,
            "decision_type": r.decision_type,
            "feedback": r.feedback,
            "created_at": r.created_at.isoformat(),
        }
        for r in recent_recs
    ]

    return TodayStateOut(
        date=date_str,
        current_time=time_str,
        user_timezone=user.timezone,
        available_minutes_today=total_flex,
        current_window=current_window_info,
        fixed_commitments=context["fixed_constraints"]["fixed_commitments"],
        flexible_windows=flexible_windows,
        urgent_obligations=context.get("urgent_obligations", []),
        tasks=context.get("ranked_tasks", []),
        goals=context.get("goals", {}).get("goals", []),
        startup=context.get("startup_state"),
        current_recommendation=rec_summary,
        attention_items=context.get("attention_items", []),
        domain_signals=context.get("domain_signals", {}),
        recent_decisions=recent_list,
    )


@router.get("/signals", response_model=list[SignalOut])
def get_signals(
    domain: str | None = Query(default=None, description="Filter by domain (e.g. STARTUP, TASKS)"),
    min_importance: float = Query(default=0.0, ge=0.0, le=1.0),
    active_only: bool = Query(default=True),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve active cross-domain signals for the user."""
    query = SignalQuery(
        user_id=user.id,
        now_utc=utcnow(),
        domains=[domain.upper()] if domain else None,
        min_importance=min_importance,
        active_only=active_only,
        limit=limit,
    )
    return signal_repo.gather_all_signals(db, user, query)


@router.get("/attention", response_model=list[AttentionItemOut])
def get_attention_items(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve prioritized attention items ranked by deterministic attention score."""
    signals = signal_repo.gather_all_signals(
        db, user, SignalQuery(user_id=user.id, now_utc=utcnow())
    )
    items = generate_attention_items(db, user, signals=signals)
    return [
        AttentionItemOut(
            id=item.id,
            type=item.type,
            domain=item.domain,
            title=item.title,
            description=item.description,
            score=item.score,
            urgency=item.urgency,
            impact=item.impact,
            provenance=item.provenance,
            deadline=item.deadline,
            suggested_action=item.suggested_action,
            source_id=item.source_id,
        )
        for item in items
    ]


@router.get("/decisions", response_model=list[DecisionHistoryOut])
def get_decision_history(
    decision_type: str | None = Query(default=None),
    feedback: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve historical decision recommendations and audit records."""
    q = db.query(AIRecommendation).filter(AIRecommendation.user_id == user.id)
    if decision_type:
        q = q.filter(AIRecommendation.decision_type == decision_type.upper())
    if feedback:
        q = q.filter(AIRecommendation.feedback == feedback.upper())
    return q.order_by(AIRecommendation.created_at.desc()).limit(limit).all()


@router.post("/feedback", response_model=DecisionFeedbackOut)
def record_decision_feedback(
    payload: DecisionFeedbackIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Record user feedback (ACCEPTED, REJECTED, DEFERRED, COMPLETED) on a recommendation."""
    valid_statuses = [s.value for s in DecisionFeedbackStatus]
    fb_upper = payload.feedback.upper()
    if fb_upper not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid feedback status. Must be one of {valid_statuses}",
        )

    rec = (
        db.query(AIRecommendation)
        .filter(
            AIRecommendation.id == payload.recommendation_id,
            AIRecommendation.user_id == user.id,
        )
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Decision recommendation not found")

    rec.feedback = fb_upper
    rec.feedback_notes = payload.notes
    rec.feedback_at = utcnow()
    db.commit()
    db.refresh(rec)

    return DecisionFeedbackOut(
        id=rec.id,
        recommendation_id=rec.id,
        feedback=rec.feedback,
        feedback_notes=rec.feedback_notes,
        feedback_at=rec.feedback_at,
        message=f"Feedback '{rec.feedback}' recorded successfully.",
    )


@router.post("/recommend", response_model=DecisionRecommendationOut)
async def get_decision_recommendation(
    available_minutes: int | None = Query(default=None, ge=5, le=24 * 60),
    current_energy: str | None = Query(default=None),
    use_ai: bool = Query(default=True),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Trigger real-time decision recommendation via AI or deterministic engine."""
    if use_ai:
        rec, _ = await decide_now(
            db,
            user,
            available_minutes=available_minutes,
            current_energy=current_energy,
        )
        return rec
    else:
        return deterministic_decision(
            db,
            user,
            available_minutes=available_minutes,
            current_energy=current_energy,
        )


# --- Recurring Schedule CRUD ---


@router.get("/recurring-schedules", response_model=list[RecurringScheduleOut])
def list_recurring_schedules(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """List all weekly recurring commitments and routine blocks for the user."""
    return (
        db.query(RecurringSchedule)
        .filter(RecurringSchedule.user_id == user.id)
        .order_by(RecurringSchedule.start_time.asc())
        .all()
    )


@router.post(
    "/recurring-schedules",
    response_model=RecurringScheduleOut,
    status_code=status.HTTP_201_CREATED,
)
def create_recurring_schedule(
    payload: RecurringScheduleIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Create a weekly recurring commitment or routine block."""
    sched = RecurringSchedule(
        user_id=user.id,
        name=payload.name,
        type=payload.type,
        days_of_week=payload.days_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
        is_hard_constraint=payload.is_hard_constraint,
        status=payload.status,
        extra_data=payload.extra_data or {},
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return sched


@router.patch("/recurring-schedules/{schedule_id}", response_model=RecurringScheduleOut)
def update_recurring_schedule(
    schedule_id: int,
    payload: RecurringScheduleUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Update an existing recurring commitment."""
    sched = (
        db.query(RecurringSchedule)
        .filter(
            RecurringSchedule.id == schedule_id,
            RecurringSchedule.user_id == user.id,
        )
        .first()
    )
    if not sched:
        raise HTTPException(status_code=404, detail="Recurring schedule not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, val in update_data.items():
        setattr(sched, field_name, val)

    db.commit()
    db.refresh(sched)
    return sched


@router.delete("/recurring-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_schedule(
    schedule_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a recurring commitment."""
    sched = (
        db.query(RecurringSchedule)
        .filter(
            RecurringSchedule.id == schedule_id,
            RecurringSchedule.user_id == user.id,
        )
        .first()
    )
    if not sched:
        raise HTTPException(status_code=404, detail="Recurring schedule not found")

    db.delete(sched)
    db.commit()
