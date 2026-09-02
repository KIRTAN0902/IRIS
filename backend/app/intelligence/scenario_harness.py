"""Decision Scenario Simulation Harness.

Provides a unified test and evaluation harness for simulating realistic life situations
and evaluating decision quality without hard-coded scenario if/else statements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.decision_engine import decide_now, deterministic_decision
from app.intelligence.recommendation import DecisionRecommendationOut, DecisionType
from app.models.enums import GoalStatus, LifeArea, TaskPriority, TaskStatus
from app.models.goal import Goal
from app.models.recurring_schedule import RecurringSchedule
from app.models.task import Task
from app.models.user import User


@dataclass
class TaskDefinition:
    title: str
    area: str = LifeArea.STARTUP.value
    priority: str = TaskPriority.MEDIUM.value
    deadline: datetime | None = None
    estimated_duration: int | None = 60
    energy_level: str | None = None
    status: str = TaskStatus.TODO.value
    goal_name: str | None = None
    depends_on_title: str | None = None


@dataclass
class GoalDefinition:
    name: str
    area: str = LifeArea.STARTUP.value
    target_value: float | None = None
    current_value: float = 0
    unit: str | None = None
    status: str = GoalStatus.ACTIVE.value
    deadline: datetime | None = None


@dataclass
class DecisionScenario:
    scenario_id: str
    name: str
    description: str
    simulated_now: datetime
    available_minutes: int | None = None
    current_energy: str | None = None
    tasks: list[TaskDefinition] = field(default_factory=list)
    goals: list[GoalDefinition] = field(default_factory=list)
    schedule: list[dict[str, Any]] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    startup_state: dict[str, Any] | None = None
    facts_override: dict[str, Any] | None = None
    preferences_override: dict[str, Any] | None = None
    expected_decision_type: DecisionType | list[DecisionType] | None = None
    expected_area: str | list[str] | None = None


@dataclass
class ScenarioEvaluationResult:
    scenario_id: str
    scenario_name: str
    recommendation: DecisionRecommendationOut
    source: str
    passed: bool
    checks: dict[str, bool]
    decision_type: str
    title: str
    reason: str
    expected_outcome: str | None
    duration_minutes: int | None
    opportunity_cost: str | None
    confidence: float
    human_evaluation_template: str


def setup_scenario_state(db: Session, user: User, scenario: DecisionScenario) -> None:
    """Populate database state for the given scenario."""
    # 1. Update user facts and preferences
    if scenario.facts_override:
        user.facts = {**(user.facts or {}), **scenario.facts_override}
    if scenario.preferences_override:
        user.preferences = {**(user.preferences or {}), **scenario.preferences_override}
    db.commit()

    # 2. Add Goals
    goal_map: dict[str, Goal] = {}
    for g_def in scenario.goals:
        g = Goal(
            user_id=user.id,
            name=g_def.name,
            area=g_def.area,
            target_value=g_def.target_value,
            current_value=g_def.current_value,
            unit=g_def.unit,
            status=g_def.status,
            deadline=g_def.deadline,
        )
        db.add(g)
        db.flush()
        goal_map[g_def.name] = g

    # 3. Add Tasks
    task_map: dict[str, Task] = {}
    for t_def in scenario.tasks:
        g_id = (
            goal_map[t_def.goal_name].id
            if t_def.goal_name and t_def.goal_name in goal_map
            else None
        )
        t = Task(
            user_id=user.id,
            title=t_def.title,
            area=t_def.area,
            priority=t_def.priority,
            deadline=t_def.deadline,
            estimated_duration=t_def.estimated_duration,
            energy_level=t_def.energy_level,
            status=t_def.status,
            goal_id=g_id,
        )
        db.add(t)
        db.flush()
        task_map[t_def.title] = t

    # 4. Add Recurring Schedules if provided
    for s_def in scenario.schedule:
        s = RecurringSchedule(
            user_id=user.id,
            name=s_def["name"],
            type=s_def.get("type", "FIXED"),
            days_of_week=s_def.get("days_of_week", "Mon,Tue,Wed,Thu,Fri,Sat,Sun"),
            start_time=s_def["start_time"],
            end_time=s_def["end_time"],
            is_hard_constraint=s_def.get("is_hard_constraint", True),
        )
        db.add(s)

    # 5. Add Signals if provided
    from app.models.signal import Signal

    for sig_def in scenario.signals:
        sig = Signal(
            user_id=user.id,
            domain=sig_def["domain"],
            signal_type=sig_def["signal_type"],
            source=sig_def.get("source", "INTERNAL_TASKS"),
            provenance=sig_def.get("provenance", "SYSTEM_DERIVED"),
            importance=sig_def.get("importance", 0.5),
            urgency=sig_def.get("urgency", 0.5),
            title=sig_def["title"],
            summary=sig_def.get("summary"),
            payload=sig_def.get("payload", {}),
            timestamp=sig_def.get("timestamp", scenario.simulated_now),
            expires_at=sig_def.get("expires_at"),
            is_active=sig_def.get("is_active", True),
        )
        db.add(sig)

    db.commit()


async def evaluate_scenario(
    db: Session,
    user: User,
    scenario: DecisionScenario,
    *,
    use_ai: bool = False,
) -> ScenarioEvaluationResult:
    """Run the decision engine against the scenario and validate quality metrics."""
    setup_scenario_state(db, user, scenario)

    if use_ai:
        rec, source = await decide_now(
            db,
            user,
            available_minutes=scenario.available_minutes,
            current_energy=scenario.current_energy,
        )
    else:
        rec = deterministic_decision(
            db,
            user,
            available_minutes=scenario.available_minutes,
            current_energy=scenario.current_energy,
        )
        source = "DETERMINISTIC"

    # Quality Checks
    checks: dict[str, bool] = {}

    # Check 1: Constraint compliance (Duration cannot exceed requested window)
    if scenario.available_minutes and rec.duration_minutes:
        checks["constraint_compliant"] = rec.duration_minutes <= scenario.available_minutes
    else:
        checks["constraint_compliant"] = True

    # Check 2: Outcome orientation (Must have non-empty reason and expected outcome)
    checks["outcome_oriented"] = bool(rec.reason and rec.expected_outcome)

    # Check 3: Area alignment (if expected area specified)
    if scenario.expected_area:
        expected_areas = (
            scenario.expected_area
            if isinstance(scenario.expected_area, list)
            else [scenario.expected_area]
        )
        # Find area of recommended task or decision
        rec_area = None
        if rec.task_id:
            t = db.query(Task).filter(Task.id == rec.task_id).first()
            if t:
                rec_area = t.area
        checks["area_aligned"] = rec_area in expected_areas if rec_area else True
    else:
        checks["area_aligned"] = True

    # Check 4: Decision type alignment (if expected decision type specified)
    if scenario.expected_decision_type:
        expected_types = (
            scenario.expected_decision_type
            if isinstance(scenario.expected_decision_type, list)
            else [scenario.expected_decision_type]
        )
        checks["decision_type_aligned"] = rec.decision_type in expected_types
    else:
        checks["decision_type_aligned"] = True

    passed = all(checks.values())

    template = f"""--------------------------------------------------------------------------------
Scenario: {scenario.name}
Description: {scenario.description}
IRIS Recommendation:
  Action: {rec.title}
  Type: {rec.decision_type}
  Duration: {rec.duration_minutes}m
  Reason: {rec.reason}
  Expected Outcome: {rec.expected_outcome}
  Opportunity Cost: {rec.opportunity_cost or "None"}
  Confidence: {rec.confidence:.2f} (Source: {source})

Human Evaluation:
  Rating (1-5): [   ]
  Correct Decision? YES / NO / PARTIAL
  Notes:
--------------------------------------------------------------------------------"""

    return ScenarioEvaluationResult(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        recommendation=rec,
        source=source,
        passed=passed,
        checks=checks,
        decision_type=rec.decision_type,
        title=rec.title,
        reason=rec.reason,
        expected_outcome=rec.expected_outcome,
        duration_minutes=rec.duration_minutes,
        opportunity_cost=rec.opportunity_cost,
        confidence=rec.confidence,
        human_evaluation_template=template,
    )
