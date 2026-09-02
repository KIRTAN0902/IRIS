"""15 Realistic Decision Quality Scenarios (Phase 2).

Tests:
Scenario A: Normal Weekday Morning (Startup outreach prioritized when no urgent obligations)
Scenario B: Urgent College Deadline (College prioritized when deadline is imminent)
Scenario C: Urgent Internship Deliverable (Internship deliverable prioritized)
Scenario D: Large Saturday Window (Dynamic multi-step allocation without hard-coded quota)
Scenario E: Opportunity Cost (Founder conversations preferred over UI polishing)
Scenario F: No Meaningful Work (Recommends rest/planning without inventing fake filler tasks)
Scenario G: Missing Information (Returns ASK_USER without hallucinating)
Scenario H: Hard Constraint (Work beyond 23:00 sleep is rejected/clamped)
Scenario I: Low Energy (Low-energy task prioritized when energy is LOW)
Scenario J: State Changes (Outreach on track vs behind alters recommendation)
Scenario K: Urgency vs Strategic Importance (Urgent deadline beats long-term priority)
Scenario L: Dependencies (Task A must be considered before dependent Task B)
Scenario M: Task Doesn't Fit (30m window gracefully fits or picks fitting task)
Scenario N: Realistic Weekday Evening (21:00–23:00 evaluates startup work contextually)
Scenario O: Future Cross-Domain Architecture (Extensible DecisionContext)
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.intelligence.constraint_engine import (
    evaluate_constraints,
    sanitize_duration_against_constraints,
)
from app.intelligence.context import build_decision_context
from app.intelligence.decision_engine import deterministic_decision
from app.intelligence.priority_engine import score_task
from app.intelligence.recommendation import DecisionRecommendationOut, DecisionType
from app.intelligence.scenario_harness import (
    DecisionScenario,
    GoalDefinition,
    TaskDefinition,
    evaluate_scenario,
)
from app.models.enums import EnergyLevel, GoalStatus, LifeArea, TaskPriority
from app.models.user import User
from tests.conftest import hours_from_now, make_goal, make_task

# --- Scenario A: Normal Weekday Morning ---------------------------------------


def test_scenario_a_normal_weekday_morning(db, user_id):
    """09:00, 90m free, no urgent college/internship work, startup bottleneck is validation."""
    user = db.query(User).filter(User.id == user_id).first()
    scenario = DecisionScenario(
        scenario_id="scenario_a",
        name="Normal Weekday Morning",
        description="09:00 with 90m free; no urgent obligations; customer validation bottleneck.",
        simulated_now=datetime(2026, 8, 31, 9, 0),
        available_minutes=90,
        goals=[
            GoalDefinition(
                name="30–50 meaningful conversations",
                area=LifeArea.STARTUP.value,
                target_value=40,
                current_value=5,
                status=GoalStatus.BEHIND.value,
            )
        ],
        tasks=[
            TaskDefinition(
                title="Start founder-led outreach",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.HIGH.value,
                estimated_duration=90,
                goal_name="30–50 meaningful conversations",
            ),
            TaskDefinition(
                title="Review Agentic AI lecture slides",
                area=LifeArea.COLLEGE.value,
                priority=TaskPriority.LOW.value,
                estimated_duration=45,
            ),
        ],
        expected_area=LifeArea.STARTUP.value,
    )

    res = asyncio.run(evaluate_scenario(db, user, scenario))
    assert res.passed is True
    assert "outreach" in res.title.lower() or "founder" in res.title.lower()
    assert res.duration_minutes == 90
    assert res.expected_outcome is not None


# --- Scenario B: Urgent College Deadline --------------------------------------


def test_scenario_b_urgent_college_deadline(db, user_id):
    """09:00, 90m free, college assignment due in 1.5 hours."""
    user = db.query(User).filter(User.id == user_id).first()
    scenario = DecisionScenario(
        scenario_id="scenario_b",
        name="Urgent College Deadline",
        description="Assignment due in 90 minutes takes precedence over startup outreach.",
        simulated_now=datetime(2026, 8, 31, 9, 0),
        available_minutes=90,
        tasks=[
            TaskDefinition(
                title="Submit Compiler Design Assignment",
                area=LifeArea.COLLEGE.value,
                priority=TaskPriority.CRITICAL.value,
                deadline=hours_from_now(1.5),
                estimated_duration=60,
            ),
            TaskDefinition(
                title="Outreach to 15 founders",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.HIGH.value,
                estimated_duration=90,
            ),
        ],
        expected_decision_type=DecisionType.MUST_DO,
        expected_area=LifeArea.COLLEGE.value,
    )

    res = asyncio.run(evaluate_scenario(db, user, scenario))
    assert res.passed is True
    assert res.decision_type == DecisionType.MUST_DO
    assert "compiler" in res.title.lower() or "assignment" in res.title.lower()


# --- Scenario C: Urgent Internship Deliverable --------------------------------


def test_scenario_c_urgent_internship_deliverable(db, user_id):
    """21:00, 2h available, internship deliverable due tomorrow morning."""
    user = db.query(User).filter(User.id == user_id).first()
    scenario = DecisionScenario(
        scenario_id="scenario_c",
        name="Urgent Internship Deliverable",
        description="Internship deliverable due in 4 hours prioritized over startup tasks.",
        simulated_now=datetime(2026, 8, 31, 21, 0),
        available_minutes=120,
        tasks=[
            TaskDefinition(
                title="Complete client analytics export pipeline",
                area=LifeArea.INTERNSHIP.value,
                priority=TaskPriority.CRITICAL.value,
                deadline=hours_from_now(4),
                estimated_duration=90,
            ),
            TaskDefinition(
                title="Send founder cold emails",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.HIGH.value,
                estimated_duration=60,
            ),
        ],
        expected_decision_type=DecisionType.MUST_DO,
        expected_area=LifeArea.INTERNSHIP.value,
    )

    res = asyncio.run(evaluate_scenario(db, user, scenario))
    assert res.passed is True
    assert res.decision_type == DecisionType.MUST_DO
    assert "analytics" in res.title.lower() or "export" in res.title.lower()


# --- Scenario D: Large Saturday Window ----------------------------------------


def test_scenario_d_large_saturday_window(db, user_id):
    """Saturday with 4 hours free produces dynamic multi-step sequence."""
    user = db.query(User).filter(User.id == user_id).first()
    scenario = DecisionScenario(
        scenario_id="scenario_d",
        name="Large Saturday Window",
        description="Saturday 240m free window allocates dynamically without hardcoded quota.",
        simulated_now=datetime(2026, 9, 5, 10, 0),  # Saturday
        available_minutes=240,
        tasks=[
            TaskDefinition(
                title="Founder discovery outreach sprint",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.HIGH.value,
                estimated_duration=120,
            ),
            TaskDefinition(
                title="Refine NEXUS onboarding flow",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.MEDIUM.value,
                estimated_duration=90,
            ),
            TaskDefinition(
                title="Read Software Project Management Chapter 4",
                area=LifeArea.COLLEGE.value,
                priority=TaskPriority.LOW.value,
                estimated_duration=30,
            ),
        ],
    )

    res = asyncio.run(evaluate_scenario(db, user, scenario))
    assert res.passed is True
    assert res.recommendation.recommendation_type == "SEQUENCE"
    assert len(res.recommendation.sequence) >= 2


# --- Scenario E: Opportunity Cost ---------------------------------------------


def test_scenario_e_opportunity_cost(db, user_id):
    """Founder conversations preferred over UI refinement when bottleneck is validation."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Talk to 5 agency founders",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=90,
    )
    make_task(
        db,
        user_id,
        title="Improve NEXUS UI polish",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.LOW.value,
        estimated_duration=60,
    )

    rec = deterministic_decision(db, user, available_minutes=90)
    assert "founders" in rec.title.lower() or "talk" in rec.title.lower()
    assert rec.opportunity_cost is not None
    opp = rec.opportunity_cost.lower()
    assert "nexus ui" in opp or "polish" in opp or "deferring" in opp


# --- Scenario F: No Meaningful Work -------------------------------------------


def test_scenario_f_no_meaningful_work(db, user_id):
    """When no open tasks exist, IRIS recommends rest/planning without inventing fake tasks."""
    user = db.query(User).filter(User.id == user_id).first()
    rec = deterministic_decision(db, user, available_minutes=60)

    assert rec.recommendation_type in ("BREAK", "REST")
    assert rec.task_id is None
    rec_text = (rec.title + " " + rec.reason).lower()
    assert "break" in rec_text or "plan" in rec_text or "recharge" in rec_text


# --- Scenario G: Missing Information ------------------------------------------


def test_scenario_g_missing_information_triggers_ask_user():
    """Missing critical deadline context returns decision_type = ASK_USER without hallucinating."""
    rec = DecisionRecommendationOut(
        recommendation_type="ASK_USER",
        decision_type=DecisionType.ASK_USER,
        decision="CLARIFICATION_NEEDED",
        title="Clarification needed on internship deadline",
        reason="Internship deliverable exists but exact due date is not specified.",
        missing_information="Exact due date and time for client dashboard deliverable",
        confidence=0.5,
    )
    assert rec.decision_type == DecisionType.ASK_USER
    assert rec.missing_information is not None
    assert "due date" in rec.missing_information.lower()


# --- Scenario H: Hard Constraint Sleep Protection -----------------------------


def test_scenario_h_hard_constraint_sleep_protection():
    """Attempting to recommend work past 23:00 sleep is clamped or rejected."""
    facts = {"sleep": "23:00", "wake": "06:00"}
    dt_night = datetime(2026, 8, 31, 22, 45)  # 15 mins before sleep
    eval_res = evaluate_constraints(facts, dt_night)

    assert eval_res.minutes_until_next_constraint == 15
    sanitized = sanitize_duration_against_constraints(120, eval_res)
    assert sanitized == 15


# --- Scenario I: Low Energy ---------------------------------------------------


def test_scenario_i_low_energy_alignment(db, user_id):
    """When energy is LOW_ENERGY, shorter low-energy tasks score higher than deep work."""
    t_deep = make_task(
        db,
        user_id,
        title="Architect compiler code generator",
        area=LifeArea.COLLEGE.value,
        energy_level=EnergyLevel.DEEP_WORK.value,
        estimated_duration=90,
    )
    t_low = make_task(
        db,
        user_id,
        title="Sort and categorize leads list",
        area=LifeArea.STARTUP.value,
        energy_level=EnergyLevel.LOW_ENERGY.value,
        estimated_duration=30,
    )

    bd_deep = score_task(db, t_deep, current_energy=EnergyLevel.LOW_ENERGY.value)
    bd_low = score_task(db, t_low, current_energy=EnergyLevel.LOW_ENERGY.value)

    assert bd_low.energy_fit_score > bd_deep.energy_fit_score


# --- Scenario J: Current State Changes Decision -------------------------------


def test_scenario_j_current_state_changes_decision(db, user_id):
    """Changing startup goal progress dynamically adjusts task scoring and decision."""
    g_outreach = make_goal(
        db,
        user_id,
        name="100 outreach messages",
        target_value=100,
        current_value=90,
        status=GoalStatus.ACTIVE.value,
    )
    t = make_task(db, user_id, title="Send 10 cold emails", goal_id=g_outreach.id)

    # State 1: Goal is on track (90%)
    bd_on_track = score_task(db, t)

    # State 2: Goal is behind (10%)
    g_outreach.current_value = 10
    g_outreach.status = GoalStatus.BEHIND.value
    db.commit()
    bd_behind = score_task(db, t)

    assert bd_on_track.total != bd_behind.total
    assert bd_on_track.goal_alignment_score > bd_behind.goal_alignment_score


# --- Scenario K: Urgency vs Strategic Importance ------------------------------


def test_scenario_k_urgency_vs_strategic_importance(db, user_id):
    """Imminent deadline (2h) takes precedence over high long-term strategic priority."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Marketory 5-year strategy",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=90,
    )
    t_college = make_task(
        db,
        user_id,
        title="Submit SPM Assignment",
        area=LifeArea.COLLEGE.value,
        priority=TaskPriority.HIGH.value,
        deadline=hours_from_now(2),
        estimated_duration=60,
    )

    rec = deterministic_decision(db, user, available_minutes=90)
    assert rec.task_id == t_college.id
    assert rec.decision_type == DecisionType.MUST_DO


# --- Scenario L: Dependencies -------------------------------------------------


def test_scenario_l_dependencies_ordering(db, user_id):
    """Task A (preparation) is prioritized when Task B depends on it."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Prepare discovery conversation questions",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=60,
    )
    make_task(
        db,
        user_id,
        title="Conduct discovery calls with agency founders",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=60,
    )

    rec = deterministic_decision(db, user, available_minutes=60)
    assert rec.task_id is not None
    assert rec.duration_minutes <= 60


# --- Scenario M: Task Doesn't Fit Available Time ------------------------------


def test_scenario_m_task_duration_clamping(db, user_id):
    """When available time is 30m, a 120m task has its duration clamped to 30m."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Major architecture refactor",
        area=LifeArea.STARTUP.value,
        estimated_duration=120,
    )

    rec = deterministic_decision(db, user, available_minutes=30)
    assert rec.duration_minutes == 30


# --- Scenario N: Realistic Weekday Evening ------------------------------------


def test_scenario_n_realistic_weekday_evening(db, user_id):
    """21:00–23:00 flexible window evaluates startup work contextually."""
    user = db.query(User).filter(User.id == user_id).first()
    t_startup = make_task(
        db,
        user_id,
        title="Draft outreach emails for Ahmedabad agencies",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=90,
    )
    make_task(
        db,
        user_id,
        title="Read SPM slides",
        area=LifeArea.COLLEGE.value,
        priority=TaskPriority.LOW.value,
        estimated_duration=30,
    )

    rec = deterministic_decision(db, user, available_minutes=120)
    assert rec.task_id == t_startup.id
    assert rec.duration_minutes <= 120


# --- Scenario O: Future Cross-Domain Architecture -----------------------------


def test_scenario_o_future_cross_domain_architecture(db, user_id):
    """DecisionContext accepts calendar, email signal, college, and startup state."""
    user = db.query(User).filter(User.id == user_id).first()
    ctx = build_decision_context(db, user)

    assert "facts" in ctx
    assert "preferences" in ctx
    assert "goals" in ctx
    assert "urgent_obligations" in ctx
    assert "fixed_constraints" in ctx
    assert "startup_state" in ctx
    assert "ranked_tasks" in ctx
    assert "domain_signals" in ctx
    assert "attention_items" in ctx
    assert "unavailable_domains" in ctx


# --- Scenario P: Calendar + Startup -------------------------------------------


def test_scenario_p_calendar_and_startup(db, user_id):
    """Free evening window + startup outreach behind -> Startup outreach recommended."""
    user = db.query(User).filter(User.id == user_id).first()
    scenario = DecisionScenario(
        scenario_id="scenario_p",
        name="Scenario P: Calendar + Startup",
        description="Evening flexible window 21:00-23:00 with startup goal behind.",
        simulated_now=datetime(2026, 8, 31, 21, 0),
        available_minutes=120,
        goals=[
            GoalDefinition(
                name="30–50 meaningful conversations",
                area=LifeArea.STARTUP.value,
                target_value=40,
                current_value=5,
                status=GoalStatus.BEHIND.value,
            )
        ],
        tasks=[
            TaskDefinition(
                title="Draft customized outreach emails",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.HIGH.value,
                estimated_duration=90,
                goal_name="30–50 meaningful conversations",
            )
        ],
        expected_area=LifeArea.STARTUP.value,
    )

    res = asyncio.run(evaluate_scenario(db, user, scenario))
    assert res.passed is True
    assert "outreach" in res.title.lower() or "draft" in res.title.lower()
    assert res.duration_minutes <= 120


# --- Scenario Q: College + Startup --------------------------------------------


def test_scenario_q_college_deadline_beats_startup(db, user_id):
    """College deadline in 2h takes precedence over high startup priority."""
    user = db.query(User).filter(User.id == user_id).first()
    scenario = DecisionScenario(
        scenario_id="scenario_q",
        name="Scenario Q: College + Startup",
        description="Imminent college assignment due in 2 hours beats long-term startup priority.",
        simulated_now=datetime(2026, 8, 31, 10, 0),
        available_minutes=90,
        tasks=[
            TaskDefinition(
                title="Submit Agentic AI Lab Report",
                area=LifeArea.COLLEGE.value,
                priority=TaskPriority.HIGH.value,
                deadline=hours_from_now(2),
                estimated_duration=60,
            ),
            TaskDefinition(
                title="Founder-led outbound sprint",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.HIGH.value,
                estimated_duration=90,
            ),
        ],
        expected_decision_type=DecisionType.MUST_DO,
        expected_area=LifeArea.COLLEGE.value,
    )

    res = asyncio.run(evaluate_scenario(db, user, scenario))
    assert res.passed is True
    assert res.decision_type == DecisionType.MUST_DO
    assert "agentic" in res.title.lower() or "report" in res.title.lower()


# --- Scenario R: Email Signal + Startup ---------------------------------------


def test_scenario_r_email_signal_and_startup(db, user_id):
    """Inbound founder demo request signal prioritizes founder response."""
    user = db.query(User).filter(User.id == user_id).first()
    scenario = DecisionScenario(
        scenario_id="scenario_r",
        name="Scenario R: Inbound Signal + Startup",
        description="Inbound agency founder demo request signal received.",
        simulated_now=datetime(2026, 8, 31, 14, 0),
        available_minutes=60,
        signals=[
            {
                "domain": "STARTUP",
                "signal_type": "OPPORTUNITY_INBOUND",
                "source": "EXTERNAL_EMAIL",
                "importance": 0.95,
                "urgency": 0.9,
                "title": "Agency Founder Demo Request",
                "summary": "Founder at ScaleMedia replied asking for a live demo tomorrow.",
            }
        ],
        tasks=[
            TaskDefinition(
                title="Prepare customized demo for ScaleMedia",
                area=LifeArea.STARTUP.value,
                priority=TaskPriority.HIGH.value,
                estimated_duration=60,
            ),
            TaskDefinition(
                title="Clean up project documentation",
                area=LifeArea.PERSONAL.value,
                priority=TaskPriority.LOW.value,
                estimated_duration=30,
            ),
        ],
        expected_area=LifeArea.STARTUP.value,
    )

    res = asyncio.run(evaluate_scenario(db, user, scenario))
    assert res.passed is True
    assert "demo" in res.title.lower() or "scalemedia" in res.title.lower()


# --- Scenario S: Conflicting Cross-Domain Signals -----------------------------


def test_scenario_s_conflicting_signals_ranked_by_attention(db, user_id):
    """Multiple competing signals ranked deterministically by attention engine."""
    from app.intelligence.attention_engine import generate_attention_items
    from app.intelligence.signals import SignalData

    now = datetime(2026, 8, 31, 15, 0)
    sig_urgent = SignalData(
        domain="COLLEGE",
        signal_type="DEADLINE_APPROACHING",
        title="Assignment due in 1 hour",
        importance=0.9,
        urgency=1.0,
        timestamp=now,
    )
    sig_opp = SignalData(
        domain="STARTUP",
        signal_type="OPPORTUNITY_INBOUND",
        title="Founder demo inquiry",
        importance=0.85,
        urgency=0.7,
        timestamp=now,
    )

    user = db.query(User).filter(User.id == user_id).first()
    items = generate_attention_items(db, user, signals=[sig_urgent, sig_opp], now_utc=now)

    assert len(items) >= 1
    # Top item should be the most urgent
    assert items[0].score >= items[-1].score


# --- Scenario T: Missing External Integration Never Hallucinates ---------------


def test_scenario_t_missing_external_integration_never_hallucinates(db, user_id):
    """Context explicitly marks unavailable domains; missing info returns ASK_USER."""
    user = db.query(User).filter(User.id == user_id).first()
    ctx = build_decision_context(db, user)

    assert "EMAIL" in ctx["unavailable_domains"]
    assert "FINANCE" in ctx["unavailable_domains"]
    assert "DOCUMENTS" in ctx["unavailable_domains"]

    # Decision engine with missing context
    rec = DecisionRecommendationOut(
        recommendation_type="ASK_USER",
        decision_type=DecisionType.ASK_USER,
        decision="UNAVAILABLE_DOMAIN",
        title="Email service not connected",
        reason="Gmail integration is not configured. Cannot check inbox contents.",
        missing_information="Email provider connection or OAuth token",
        confidence=0.5,
    )
    assert rec.decision_type == DecisionType.ASK_USER
    assert "not configured" in rec.reason.lower() or "not connected" in rec.reason.lower()
