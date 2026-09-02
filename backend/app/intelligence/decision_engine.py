"""Decision Engine -- Main entry point for IRIS Decision Intelligence.

Orchestrates:
1. Snapshot context generation (Facts, Preferences, Goals, Constraints, State, Resources)
2. Deterministic baseline analysis & contextual fallback
3. Gemini AI reasoning with guardrails & trade-off evaluation
4. Recommendation audit persistence in ai_recommendations table
5. Structured decision return
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.context import build_decision_context
from app.intelligence.priority_engine import rank_tasks
from app.intelligence.reasoning import reason_over_context
from app.intelligence.recommendation import (
    AlternativeOption,
    DecisionRecommendationOut,
    DecisionStep,
    DecisionType,
)
from app.models.ai_recommendation import AIRecommendation
from app.models.enums import LifeArea, TaskStatus
from app.models.task import Task
from app.models.user import User
from app.utils.datetime import to_local, utcnow


def deterministic_decision(
    db: Session,
    user: User,
    *,
    available_minutes: int | None = None,
    window_start=None,
    window_end=None,
    current_energy: str | None = None,
) -> DecisionRecommendationOut:
    """Computes a high-quality deterministic contextual recommendation.

    Works without AI: evaluates constraints, urgent obligations, startup bottlenecks,
    task fit, and trade-offs.
    """
    now = utcnow()
    context = build_decision_context(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
        current_energy=current_energy,
    )

    constraints = context["fixed_constraints"]
    effective_minutes = context["available_minutes"]

    # 1. Hard constraint check: if user is currently inside sleep window and gave no window
    if available_minutes is None and constraints["is_in_hard_constraint"]:
        active = constraints["active_constraint_name"] or "Rest"
        if active.lower() == "sleep":
            return DecisionRecommendationOut(
                recommendation_type="REST",
                decision_type=DecisionType.WAIT,
                decision="REST_AND_SLEEP",
                title=f"Sleep window ({constraints['hard_sleep_time']})",
                reason=(
                    "Current time is within your configured sleep schedule. "
                    "Rest and recharge for tomorrow."
                ),
                duration_minutes=None,
                expected_outcome="Rest and recovery",
                confidence=0.95,
                opportunity_cost=(
                    "Working during sleep compromises cognitive performance tomorrow."
                ),
            )

    open_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
        )
        .all()
    )

    if not open_tasks:
        return DecisionRecommendationOut(
            recommendation_type="BREAK",
            decision_type=DecisionType.WAIT,
            decision="NO_OPEN_TASKS",
            title="Take a break or plan upcoming goals",
            reason=(
                "No open tasks found in your task pool. "
                "Recharge, reflect, or define new milestones."
            ),
            duration_minutes=effective_minutes or 30,
            expected_outcome="Recharge and plan ahead",
            confidence=1.0,
        )

    ranked_pairs = rank_tasks(
        db,
        open_tasks,
        available_minutes=effective_minutes,
        current_energy=current_energy,
        now=now,
    )

    top_task, top_breakdown = ranked_pairs[0]
    has_imminent_deadline = top_breakdown.deadline_score >= 28 or top_task.is_overdue

    alternatives = []
    if len(ranked_pairs) > 1:
        for alt_task, alt_bd in ranked_pairs[1:4]:
            alternatives.append(
                AlternativeOption(
                    title=alt_task.title,
                    area=alt_task.area,
                    trade_off_reason=(
                        f"Ranked lower (score {alt_bd.total}) due to lower "
                        "urgency or fit compared to top task."
                    ),
                )
            )

    # Multi-step sequence when large flexible window is available (>= 120m)
    sequence_steps: list[DecisionStep] = []
    if effective_minutes and effective_minutes >= 120 and len(ranked_pairs) >= 2:
        rem_min = effective_minutes
        step_idx = 1
        for t_item, bd_item in ranked_pairs[:4]:
            t_dur = t_item.estimated_duration or 45
            allocated = min(t_dur, rem_min)
            if allocated <= 0:
                break
            sequence_steps.append(
                DecisionStep(
                    step_number=step_idx,
                    title=t_item.title,
                    task_id=t_item.id,
                    area=t_item.area,
                    duration_minutes=allocated,
                    reason=bd_item.notes[0] if bd_item.notes else f"Priority {bd_item.total}",
                    expected_outcome=f"Complete '{t_item.title}'",
                )
            )
            rem_min -= allocated
            step_idx += 1
            if rem_min < 15:
                break

    # Construct contextual reason and decision type
    reason_parts = []
    decision_type = DecisionType.SHOULD_DO
    decision_key = "EXECUTE_TASK"

    if top_task.is_overdue:
        decision_type = DecisionType.MUST_DO
        decision_key = f"{top_task.area}_OVERDUE"
        reason_parts.append("Overdue task requiring immediate completion")
    elif has_imminent_deadline and top_task.deadline:
        decision_type = DecisionType.MUST_DO
        decision_key = f"{top_task.area}_DEADLINE"
        local_dl = to_local(top_task.deadline, user.timezone).strftime("%a %H:%M")
        reason_parts.append(f"Urgent deadline due {local_dl} ({user.timezone})")
    elif top_task.area == LifeArea.STARTUP.value:
        is_outreach = "outreach" in top_task.title.lower() or "contact" in top_task.title.lower()
        decision_key = "STARTUP_OUTREACH" if is_outreach else "STARTUP_EXECUTION"
        reason_parts.append(
            "Startup is your primary strategic priority and customer validation is the focus"
        )
        if top_task.goal_id:
            reason_parts.append("directly aligns with active startup milestone")
    else:
        decision_key = f"{top_task.area}_TASK"
        reason_parts.append(f"Highest contextual priority in {top_task.area}")

    if top_breakdown.notes:
        fit_notes = [n for n in top_breakdown.notes if "Fits" in n or "window" in n]
        if fit_notes:
            reason_parts.append(fit_notes[0])

    duration = top_task.estimated_duration or 45
    if effective_minutes:
        duration = min(duration, effective_minutes)

    opp_cost = None
    if alternatives:
        alt_names = ", ".join(f"'{a.title}'" for a in alternatives[:2])
        opp_cost = f"Deferring {alt_names} to prioritize immediate urgency and strategic alignment."

    confidence = 0.88 if has_imminent_deadline else (0.82 if top_breakdown.total >= 30 else 0.65)

    evidence_list = []
    observed_facts = []
    derived_insights = []

    if top_task.deadline:
        dl_str = top_task.deadline.isoformat()
        evidence_list.append(f"Task deadline: {dl_str}")
        observed_facts.append(f"Deadline set at {dl_str}")
    if top_task.priority:
        evidence_list.append(f"Priority level: {top_task.priority}")
        observed_facts.append(f"Priority is {top_task.priority}")
    if top_breakdown.notes:
        for n in top_breakdown.notes:
            derived_insights.append(n)
            evidence_list.append(n)

    return DecisionRecommendationOut(
        recommendation_type="SEQUENCE" if len(sequence_steps) > 1 else "TASK",
        decision_type=decision_type,
        decision=decision_key,
        task_id=top_task.id,
        title=top_task.title,
        reason="; ".join(reason_parts),
        duration_minutes=duration,
        expected_outcome=f"Complete '{top_task.title}'",
        confidence=confidence,
        opportunity_cost=opp_cost,
        evidence=evidence_list,
        observed_facts=observed_facts,
        derived_insights=derived_insights,
        alternatives_considered=alternatives,
        sequence=sequence_steps if len(sequence_steps) > 1 else [],
    )


async def decide_now(
    db: Session,
    user: User,
    *,
    available_minutes: int | None = None,
    window_start=None,
    window_end=None,
    current_energy: str | None = None,
) -> tuple[DecisionRecommendationOut, str]:
    """Flagship entrypoint: builds context, reasons via Gemini or deterministic engine,
    audits the recommendation, and returns the result.
    """
    fallback = deterministic_decision(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
        current_energy=current_energy,
    )

    context = build_decision_context(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
        current_energy=current_energy,
    )

    result, source = await reason_over_context(context, fallback=fallback)

    # Decision audit logging in database
    try:
        audit_row = AIRecommendation(
            user_id=user.id,
            task_id=result.task_id,
            recommendation_type=result.recommendation_type,
            decision_type=result.decision_type,
            title=result.title,
            reason=result.reason,
            expected_outcome=result.expected_outcome,
            duration_minutes=result.duration_minutes,
            confidence=result.confidence,
            source=source,
            opportunity_cost=result.opportunity_cost,
            evidence=result.evidence or [],
            context_snapshot={
                "available_minutes": context.get("available_minutes"),
                "urgent_obligations_count": len(context.get("urgent_obligations", [])),
                "top_task": result.title,
                "attention_items_count": len(context.get("attention_items", [])),
            },
            payload={
                "decision_type": result.decision_type,
                "decision": result.decision,
                "alternatives_count": len(result.alternatives_considered),
                "sequence_steps_count": len(result.sequence),
                "missing_information": result.missing_information,
            },
        )
        db.add(audit_row)
        db.commit()
    except Exception:
        db.rollback()

    return result, source
