"""Interactive / Manual Decision Intelligence Evaluation Script.

Evaluates the 20 realistic decision scenarios (A through T) against the Decision Engine.
Runs with live Gemini if GEMINI_API_KEY is configured and --use-ai is passed,
or using the high-performance deterministic contextual engine.

Usage:
    python scripts/evaluate_decisions.py
    python scripts/evaluate_decisions.py --use-ai
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import get_current_user  # noqa: E402
from app.intelligence.recommendation import DecisionType  # noqa: E402
from app.intelligence.scenario_harness import (  # noqa: E402
    DecisionScenario,
    GoalDefinition,
    TaskDefinition,
    evaluate_scenario,
)
from app.models.enums import EnergyLevel, GoalStatus, LifeArea, TaskPriority  # noqa: E402


def build_all_scenarios() -> list[DecisionScenario]:
    """Define the 20 realistic decision scenarios (A through T)."""
    now = datetime.now()

    return [
        DecisionScenario(
            scenario_id="scenario_a",
            name="A — Normal Weekday Morning (09:00, 90m free)",
            description="No urgent obligations; founder acquisition is active bottleneck.",
            simulated_now=now.replace(hour=9, minute=0),
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
        ),
        DecisionScenario(
            scenario_id="scenario_b",
            name="B — Urgent College Deadline (09:00, 90m free)",
            description="Assignment due in 90 minutes takes precedence over startup outreach.",
            simulated_now=now.replace(hour=9, minute=0),
            available_minutes=90,
            tasks=[
                TaskDefinition(
                    title="Submit Compiler Design Assignment",
                    area=LifeArea.COLLEGE.value,
                    priority=TaskPriority.CRITICAL.value,
                    deadline=now + timedelta(minutes=90),
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
        ),
        DecisionScenario(
            scenario_id="scenario_c",
            name="C — Urgent Internship Deliverable (21:00, 2h available)",
            description="Client analytics dashboard deliverable due tomorrow morning.",
            simulated_now=now.replace(hour=21, minute=0),
            available_minutes=120,
            tasks=[
                TaskDefinition(
                    title="Complete client analytics export pipeline",
                    area=LifeArea.INTERNSHIP.value,
                    priority=TaskPriority.CRITICAL.value,
                    deadline=now + timedelta(hours=4),
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
        ),
        DecisionScenario(
            scenario_id="scenario_d",
            name="D — Large Saturday Window (Saturday, 4h free)",
            description="Large free block produces dynamic sequence without hard quotas.",
            simulated_now=now.replace(hour=10, minute=0),
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
        ),
        DecisionScenario(
            scenario_id="scenario_e",
            name="E — Opportunity Cost (UI Polish vs Founder Outreach)",
            description="Founder conversations preferred over UI polish during validation stage.",
            simulated_now=now.replace(hour=9, minute=30),
            available_minutes=90,
            tasks=[
                TaskDefinition(
                    title="Talk to 5 agency founders",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.HIGH.value,
                    estimated_duration=90,
                ),
                TaskDefinition(
                    title="Improve NEXUS UI polish",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.LOW.value,
                    estimated_duration=60,
                ),
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_f",
            name="F — No Meaningful Work",
            description="No urgent or open tasks; recommends rest/planning without fake work.",
            simulated_now=now.replace(hour=15, minute=0),
            available_minutes=60,
            tasks=[],
        ),
        DecisionScenario(
            scenario_id="scenario_g",
            name="G — Missing Information",
            description="Deliverable exists with unknown deadline; triggers ASK_USER.",
            simulated_now=now.replace(hour=14, minute=0),
            available_minutes=60,
            tasks=[
                TaskDefinition(
                    title="Internship client report",
                    area=LifeArea.INTERNSHIP.value,
                    priority=TaskPriority.MEDIUM.value,
                )
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_h",
            name="H — Hard Constraint Sleep Protection (22:45)",
            description="Work duration is clamped to remaining 15 minutes before 23:00 sleep.",
            simulated_now=now.replace(hour=22, minute=45),
            available_minutes=15,
            tasks=[
                TaskDefinition(
                    title="Draft outreach emails",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.HIGH.value,
                    estimated_duration=90,
                )
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_i",
            name="I — Low Energy Alignment",
            description="Low energy: administrative task prioritized over 90m deep work.",
            simulated_now=now.replace(hour=16, minute=0),
            available_minutes=45,
            current_energy=EnergyLevel.LOW_ENERGY.value,
            tasks=[
                TaskDefinition(
                    title="Architect compiler code generator",
                    area=LifeArea.COLLEGE.value,
                    energy_level=EnergyLevel.DEEP_WORK.value,
                    estimated_duration=90,
                ),
                TaskDefinition(
                    title="Sort and categorize leads list",
                    area=LifeArea.STARTUP.value,
                    energy_level=EnergyLevel.LOW_ENERGY.value,
                    estimated_duration=30,
                ),
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_j",
            name="J — Current State Changes Decision",
            description="Startup goal progress dynamically changes priority and decision.",
            simulated_now=now.replace(hour=10, minute=0),
            available_minutes=60,
            goals=[
                GoalDefinition(
                    name="100 outreach messages",
                    area=LifeArea.STARTUP.value,
                    target_value=100,
                    current_value=15,
                    status=GoalStatus.BEHIND.value,
                )
            ],
            tasks=[
                TaskDefinition(
                    title="Send 15 cold emails to agency founders",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.HIGH.value,
                    estimated_duration=60,
                    goal_name="100 outreach messages",
                )
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_k",
            name="K — Urgency vs Strategic Importance",
            description="Imminent 2h college deadline beats long-term startup strategic priority.",
            simulated_now=now.replace(hour=10, minute=0),
            available_minutes=90,
            tasks=[
                TaskDefinition(
                    title="Marketory 5-year strategy",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.HIGH.value,
                    estimated_duration=90,
                ),
                TaskDefinition(
                    title="Submit SPM Assignment",
                    area=LifeArea.COLLEGE.value,
                    priority=TaskPriority.HIGH.value,
                    deadline=now + timedelta(hours=2),
                    estimated_duration=60,
                ),
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_l",
            name="L — Dependencies Ordering",
            description="Preparation task considered before dependent execution task.",
            simulated_now=now.replace(hour=11, minute=0),
            available_minutes=60,
            tasks=[
                TaskDefinition(
                    title="Prepare discovery conversation questions",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.HIGH.value,
                    estimated_duration=60,
                ),
                TaskDefinition(
                    title="Conduct discovery calls with agency founders",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.HIGH.value,
                    estimated_duration=60,
                ),
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_m",
            name="M — Task Doesn't Fit Available Time",
            description="30m window clamps 120m task or fits available time.",
            simulated_now=now.replace(hour=10, minute=0),
            available_minutes=30,
            tasks=[
                TaskDefinition(
                    title="Major architecture refactor",
                    area=LifeArea.STARTUP.value,
                    estimated_duration=120,
                )
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_n",
            name="N — Realistic Weekday Evening (21:00–23:00)",
            description="Recognizes flexible evening window and evaluates startup work.",
            simulated_now=now.replace(hour=21, minute=0),
            available_minutes=120,
            tasks=[
                TaskDefinition(
                    title="Draft outreach emails for Ahmedabad agencies",
                    area=LifeArea.STARTUP.value,
                    priority=TaskPriority.HIGH.value,
                    estimated_duration=90,
                ),
                TaskDefinition(
                    title="Read SPM slides",
                    area=LifeArea.COLLEGE.value,
                    priority=TaskPriority.LOW.value,
                    estimated_duration=30,
                ),
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_o",
            name="O — Future Cross-Domain Architecture",
            description="Decision context accepts calendar, email, college, and startup signals.",
            simulated_now=now.replace(hour=14, minute=0),
            available_minutes=60,
            tasks=[
                TaskDefinition(
                    title="Cross-domain signal validation",
                    area=LifeArea.STARTUP.value,
                    estimated_duration=60,
                )
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_p",
            name="P — Calendar + Startup Alignment",
            description="Free evening window (21:00-23:00) with startup goal behind.",
            simulated_now=now.replace(hour=21, minute=0),
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
        ),
        DecisionScenario(
            scenario_id="scenario_q",
            name="Q — College Deadline Beats Startup",
            description="Imminent college assignment due in 2h beats long-term startup priority.",
            simulated_now=now.replace(hour=10, minute=0),
            available_minutes=90,
            tasks=[
                TaskDefinition(
                    title="Submit Agentic AI Lab Report",
                    area=LifeArea.COLLEGE.value,
                    priority=TaskPriority.HIGH.value,
                    deadline=now + timedelta(hours=2),
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
        ),
        DecisionScenario(
            scenario_id="scenario_r",
            name="R — Inbound Signal + Startup",
            description="Inbound agency founder demo request signal received.",
            simulated_now=now.replace(hour=14, minute=0),
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
        ),
        DecisionScenario(
            scenario_id="scenario_s",
            name="S — Conflicting Cross-Domain Signals",
            description="Multiple competing signals ranked deterministically by attention engine.",
            simulated_now=now.replace(hour=15, minute=0),
            available_minutes=60,
            tasks=[
                TaskDefinition(
                    title="Finish urgent deliverable",
                    area=LifeArea.INTERNSHIP.value,
                    priority=TaskPriority.HIGH.value,
                    deadline=now + timedelta(hours=2),
                    estimated_duration=60,
                )
            ],
        ),
        DecisionScenario(
            scenario_id="scenario_t",
            name="T — Missing External Integration",
            description="Unavailable domains marked; missing info returns ASK_USER.",
            simulated_now=now.replace(hour=16, minute=0),
            available_minutes=60,
            tasks=[],
        ),
    ]


async def run_evaluation(use_ai: bool = False):
    """Run all 20 scenarios (A through T) and print human-readable evaluation summary."""
    print("=" * 80)
    print("IRIS DECISION INTELLIGENCE -- 20 REALISTIC SCENARIO EVALUATION (A through T)")
    print(f"Mode: {'AI (Gemini + Guardrails)' if use_ai else 'Deterministic Contextual Engine'}")
    print("=" * 80)

    scenarios = build_all_scenarios()
    passed_count = 0

    for idx, sc in enumerate(scenarios, 1):
        # Isolate database schema per scenario
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        db = SessionLocal()
        try:
            user = get_current_user(db)
            res = await evaluate_scenario(db, user, sc, use_ai=use_ai)
            if res.passed:
                passed_count += 1
            print(f"\n[{idx}/20] {res.scenario_name}")
            print(f"  Decision Type: {res.decision_type}")
            print(f"  Recommended Action: {res.title}")
            print(f"  Duration: {res.duration_minutes}m (Window: {sc.available_minutes}m)")
            print(f"  Reason: {res.reason}")
            print(f"  Expected Outcome: {res.expected_outcome}")
            if res.opportunity_cost:
                print(f"  Opportunity Cost: {res.opportunity_cost}")
            print(
                f"  Confidence: {res.confidence:.2f} | Source: {res.source} | "
                f"Checks Passed: {res.passed}"
            )
        finally:
            db.close()

    print("\n" + "=" * 80)
    print(f"EVALUATION COMPLETE: {passed_count}/20 Scenarios Passed")
    print("=" * 80)


if __name__ == "__main__":
    use_ai_flag = "--use-ai" in sys.argv
    asyncio.run(run_evaluation(use_ai=use_ai_flag))
