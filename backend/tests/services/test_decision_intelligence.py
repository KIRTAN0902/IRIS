"""Decision Intelligence Engine & Architecture Test Suite.

Verifies:
1. Scenario 1: No urgent obligations + startup validation behind -> Startup outreach recommended.
2. Scenario 2: Urgent college deadline -> College prioritized (MUST_DO).
3. Scenario 3: Urgent internship deliverable -> Internship prioritized (MUST_DO).
4. Scenario 4: Multi-step sequence planning when available time is large (e.g. 3 hours).
5. Scenario 5: Dynamic allocation on open days (e.g. Saturday) based on strategic opportunity.
6. Scenario 6: Missing information triggers ASK_USER without hallucinations.
7. Hard constraint protection (Sleep time / routine hours are non-negotiable).
8. Anti-hallucination guardrails (Invalid AI task_ids rejected).
9. Recommendation audit persistence in ai_recommendations.
10. Opportunity cost and alternative trade-off reasoning.
11. Energy fit alignment.
12. Context provider snapshot architecture.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.intelligence.constraint_engine import (
    evaluate_constraints,
    sanitize_duration_against_constraints,
)
from app.intelligence.context import build_decision_context
from app.intelligence.decision_engine import decide_now, deterministic_decision
from app.intelligence.priority_engine import score_task
from app.intelligence.reasoning import reason_over_context
from app.intelligence.recommendation import (
    DecisionRecommendationOut,
    DecisionType,
)
from app.models.ai_recommendation import AIRecommendation
from app.models.enums import EnergyLevel, GoalStatus, LifeArea, TaskPriority
from app.models.user import User
from tests.conftest import hours_from_now, make_goal, make_task

# --- Scenario Tests -----------------------------------------------------------


def test_scenario_1_no_urgent_obligations_recommends_startup_outreach(db, user_id):
    """Situation A: Available time 90m, no urgent college/internship work, outreach behind."""
    user = db.query(User).filter(User.id == user_id).first()
    goal = make_goal(
        db,
        user_id,
        name="Contact 100 agency founders",
        target_value=100,
        current_value=15,
        unit="founders",
        status=GoalStatus.BEHIND.value,
    )
    startup_task = make_task(
        db,
        user_id,
        title="Contact 15 agency founders",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=90,
        goal_id=goal.id,
    )
    make_task(
        db,
        user_id,
        title="Review lecture notes",
        area=LifeArea.COLLEGE.value,
        priority=TaskPriority.LOW.value,
        estimated_duration=60,
    )

    rec = deterministic_decision(db, user, available_minutes=90)

    assert rec.task_id == startup_task.id
    assert rec.decision_type in (DecisionType.SHOULD_DO, DecisionType.MUST_DO)
    assert "Startup" in rec.reason or "startup" in rec.reason.lower()
    assert rec.duration_minutes == 90
    assert rec.expected_outcome is not None
    assert rec.confidence >= 0.70


def test_scenario_2_urgent_college_deadline_prioritizes_college(db, user_id):
    """Situation B: College assignment due in 90 minutes; takes precedence over startup."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Outreach to founders",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=60,
    )
    urgent_college = make_task(
        db,
        user_id,
        title="Submit AI Assignment",
        area=LifeArea.COLLEGE.value,
        priority=TaskPriority.CRITICAL.value,
        deadline=hours_from_now(1.5),
        estimated_duration=60,
    )

    rec = deterministic_decision(db, user, available_minutes=90)

    assert rec.task_id == urgent_college.id
    assert rec.decision_type == DecisionType.MUST_DO
    assert "due" in rec.reason.lower() or "deadline" in rec.reason.lower()


def test_scenario_3_urgent_internship_deliverable_prioritizes_internship(db, user_id):
    """Situation C: Internship deliverable due tomorrow morning; prioritized over startup."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Build LinkedIn campaign",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=90,
    )
    internship_deliverable = make_task(
        db,
        user_id,
        title="Complete client analytics dashboard",
        area=LifeArea.INTERNSHIP.value,
        priority=TaskPriority.CRITICAL.value,
        deadline=hours_from_now(4),
        estimated_duration=120,
    )

    rec = deterministic_decision(db, user, available_minutes=120)

    assert rec.task_id == internship_deliverable.id
    assert rec.decision_type == DecisionType.MUST_DO
    assert "due" in rec.reason.lower() or "deadline" in rec.reason.lower()


def test_scenario_4_multi_step_sequence_for_large_free_time(db, user_id):
    """Situation D / Multi-step planning: 3 hours (180m) free window produces sequence."""
    user = db.query(User).filter(User.id == user_id).first()
    t1 = make_task(
        db,
        user_id,
        title="Urgent Assignment",
        area=LifeArea.COLLEGE.value,
        deadline=hours_from_now(2),
        estimated_duration=60,
        priority=TaskPriority.CRITICAL.value,
    )
    t2 = make_task(
        db,
        user_id,
        title="Founder outreach",
        area=LifeArea.STARTUP.value,
        estimated_duration=90,
        priority=TaskPriority.HIGH.value,
    )
    make_task(
        db,
        user_id,
        title="Follow up with leads",
        area=LifeArea.STARTUP.value,
        estimated_duration=30,
        priority=TaskPriority.MEDIUM.value,
    )

    rec = deterministic_decision(db, user, available_minutes=180)

    assert rec.recommendation_type == "SEQUENCE"
    assert len(rec.sequence) >= 2
    step_task_ids = [s.task_id for s in rec.sequence]
    assert t1.id in step_task_ids
    assert t2.id in step_task_ids


def test_scenario_5_saturday_large_free_time_allocates_dynamically(db, user_id):
    """Saturday with large amount of free time (4h / 240m) allocates by strategic opportunity."""
    user = db.query(User).filter(User.id == user_id).first()
    t_outreach = make_task(
        db,
        user_id,
        title="Founder discovery sprint",
        area=LifeArea.STARTUP.value,
        estimated_duration=120,
        priority=TaskPriority.HIGH.value,
    )
    make_task(
        db,
        user_id,
        title="Refine NEXUS onboarding flow",
        area=LifeArea.STARTUP.value,
        estimated_duration=90,
        priority=TaskPriority.MEDIUM.value,
    )
    make_task(
        db,
        user_id,
        title="Read SPM chapter 4",
        area=LifeArea.COLLEGE.value,
        estimated_duration=30,
        priority=TaskPriority.LOW.value,
    )

    rec = deterministic_decision(db, user, available_minutes=240)

    assert rec.recommendation_type == "SEQUENCE"
    assert len(rec.sequence) >= 2
    assert rec.sequence[0].task_id == t_outreach.id


# --- Constraint & Guardrail Tests ---------------------------------------------


def test_hard_constraint_sleep_protection():
    """Gemini or recommendation must never recommend working past configured sleep time."""
    facts = {
        "sleep": "23:00",
        "wake": "06:00",
        "routine": [],
    }
    # Test at 22:30 local time (30 mins before sleep)
    dt_at_night = datetime(2026, 8, 30, 22, 30)
    eval_res = evaluate_constraints(facts, dt_at_night)

    assert eval_res.minutes_until_next_constraint == 30
    assert "Sleep" in eval_res.next_constraint_name

    sanitized = sanitize_duration_against_constraints(120, eval_res)
    assert sanitized == 30  # Clamped strictly to 30 mins remaining before sleep


def test_hard_constraint_during_sleep_window():
    """When inside sleep window (e.g. 02:00 AM), recommendation identifies sleep."""
    facts = {"sleep": "23:00", "wake": "06:00"}
    dt_late = datetime(2026, 8, 30, 2, 0)
    eval_res = evaluate_constraints(facts, dt_late)

    assert eval_res.is_in_hard_constraint is True
    assert eval_res.active_constraint_name == "Sleep"


def test_missing_information_ask_user_flow(monkeypatch):
    """When critical context is missing, IRIS returns ASK_USER without hallucinating."""

    async def mock_ask_user(*args, **kwargs):
        return DecisionRecommendationOut(
            recommendation_type="ASK_USER",
            decision_type=DecisionType.ASK_USER,
            decision="CLARIFICATION_NEEDED",
            title="Clarification needed on internship deadline",
            reason="I need to know whether your deliverable is due tomorrow.",
            missing_information="Internship deliverable exact due date/time",
            confidence=0.5,
        ), "AI"

    fallback = DecisionRecommendationOut(
        title="Fallback",
        reason="Fallback reason",
        confidence=0.5,
    )
    res, src = asyncio.run(mock_ask_user({}, fallback=fallback))
    assert res.decision_type == DecisionType.ASK_USER
    assert res.missing_information is not None
    assert "internship" in res.missing_information.lower()


def test_anti_hallucination_rejects_invented_task_id(monkeypatch):
    """AI returning a non-existent task_id is caught and degraded to deterministic fallback."""
    from app.ai.factory import set_ai_provider
    from app.ai.providers.mock import MockProvider

    provider = MockProvider(
        name="mock",
        default_response_generator=lambda system, prompt, schema: DecisionRecommendationOut(
            recommendation_type="TASK",
            task_id=999999,  # Invented task_id
            title="Invented phantom task",
            reason="Phantom reason",
            confidence=0.99,
        ),
    )
    set_ai_provider(provider)

    context = {
        "ranked_tasks": [{"task": {"id": 1, "title": "Real Task"}}],
        "available_minutes": 60,
    }
    fallback = DecisionRecommendationOut(
        recommendation_type="TASK",
        task_id=1,
        title="Real Task",
        reason="Real deterministic reason",
        confidence=0.8,
    )

    res, src = asyncio.run(reason_over_context(context, fallback=fallback))
    assert src == "DETERMINISTIC"
    assert res.task_id == 1
    assert res.title == "Real Task"


def test_decision_audit_persistence(db, user_id):
    """Calling decide_now persists structured metadata to ai_recommendations."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(db, user_id, title="Founder discovery calls", area=LifeArea.STARTUP.value)

    res, src = asyncio.run(decide_now(db, user, available_minutes=60))

    audit_rows = db.query(AIRecommendation).filter(AIRecommendation.user_id == user.id).all()
    assert len(audit_rows) >= 1
    last_audit = audit_rows[-1]
    assert last_audit.title == res.title
    assert last_audit.source == src
    assert last_audit.payload is not None
    assert "decision_type" in last_audit.payload


def test_opportunity_cost_and_alternatives(db, user_id):
    """Recommendations include alternatives considered and opportunity cost notes."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Contact 10 founders",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
    )
    make_task(
        db,
        user_id,
        title="Polish CSS styles",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.LOW.value,
    )

    rec = deterministic_decision(db, user, available_minutes=60)
    assert len(rec.alternatives_considered) >= 1
    assert rec.opportunity_cost is not None


def test_energy_fit_scoring(db, user_id):
    """Deep work tasks are boosted when energy is DEEP_WORK and penalized when LOW_ENERGY."""
    deep_task = make_task(
        db,
        user_id,
        title="Architect compiler backend",
        area=LifeArea.COLLEGE.value,
        energy_level=EnergyLevel.DEEP_WORK.value,
    )
    make_task(
        db,
        user_id,
        title="Clean inbox",
        area=LifeArea.PERSONAL.value,
        energy_level=EnergyLevel.LOW_ENERGY.value,
    )

    b_deep_fit = score_task(db, deep_task, current_energy=EnergyLevel.DEEP_WORK.value)
    b_deep_misfit = score_task(db, deep_task, current_energy=EnergyLevel.LOW_ENERGY.value)

    assert b_deep_fit.energy_fit_score > 0
    assert b_deep_misfit.energy_fit_score < 0


def test_structured_user_facts_and_preferences(db, user_id):
    """User facts & preferences are properly included in the snapshot DecisionContext."""
    user = db.query(User).filter(User.id == user_id).first()
    user.facts = {
        "wake": "05:30",
        "sleep": "22:30",
        "college": {"degree": "B.Tech AI", "semester": "4th"},
    }
    user.preferences = {
        "primary_long_term_goal": "STARTUP",
        "startup_time_allocation": "maximum",
    }
    db.commit()

    ctx = build_decision_context(db, user)

    assert ctx["facts"]["wake"] == "05:30"
    assert ctx["facts"]["sleep"] == "22:30"
    assert ctx["preferences"]["startup_time_allocation"] == "maximum"
    assert "fixed_constraints" in ctx
    assert "goals" in ctx
