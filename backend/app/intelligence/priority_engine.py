"""Deterministic priority engine.

Analyzes open tasks deterministically:
- Imminent deadlines (<= 2h bonus 40 points, <= 6h, etc.)
- Overdue penalties
- Priority scores (CRITICAL, HIGH, MEDIUM, LOW)
- Goal alignment scores
- Effort fit scores (duration vs available window)
- In-progress boost
- Energy fit alignment

Strategic weighting is an input signal, never the sole dictator:
Urgent deadlines always take precedence over strategic weighting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.enums import (
    AREA_STRATEGIC_WEIGHT,
    EnergyLevel,
    GoalStatus,
    LifeArea,
    TaskPriority,
    TaskStatus,
)
from app.models.goal import Goal
from app.models.task import Task
from app.utils.datetime import clamp, minutes_between, utcnow

# --- Tunable weights ---------------------------------------------------------

DEADLINE_TIERS: list[tuple[int, float]] = [
    (2 * 60, 40),  # <= 2h away
    (6 * 60, 34),  # <= 6h
    (24 * 60, 28),  # <= 1 day
    (2 * 24 * 60, 22),
    (3 * 24 * 60, 16),
    (7 * 24 * 60, 10),
    (14 * 24 * 60, 6),
]
NO_DEADLINE_SCORE = 0.0
FAR_DEADLINE_SCORE = 3.0

PRIORITY_SCORES: dict[str, float] = {
    TaskPriority.CRITICAL: 12,
    TaskPriority.HIGH: 8,
    TaskPriority.MEDIUM: 4,
    TaskPriority.LOW: 0,
}

OVERDUE_PENALTY = 25.0
GOAL_ALIGNMENT_SCORE = 8.0
GOAL_NEAR_COMPLETION_BONUS = 3.0

EFFORT_FIT_BONUS = 6.0  # estimated duration fits available time
EFFORT_MISFIT_PENALTY = -6.0  # clearly too big for the window
IN_PROGRESS_BOOST = 3.0  # finish what you started
ENERGY_FIT_BONUS = 3.0  # energy level aligns with available window / capacity


@dataclass
class PriorityBreakdown:
    deadline_score: float = 0
    priority_score: float = 0
    strategic_score: float = 0
    goal_alignment_score: float = 0
    overdue_penalty: float = 0
    effort_fit_score: float = 0
    in_progress_boost: float = 0
    energy_fit_score: float = 0
    total: float = 0
    notes: list[str] = field(default_factory=list)


def _deadline_score(task: Task, now: datetime) -> tuple[float, str | None]:
    if task.deadline is None:
        return NO_DEADLINE_SCORE, None
    minutes = minutes_between(now, task.deadline)
    if task.is_overdue:
        return 0.0, "overdue"
    for threshold, score in DEADLINE_TIERS:
        if minutes <= threshold:
            note = f"due in {minutes}m" if minutes < 24 * 60 else f"due in {minutes // (24 * 60)}d"
            return score, note
    return FAR_DEADLINE_SCORE, None


def _strategic_score(area: str) -> float:
    weight = AREA_STRATEGIC_WEIGHT.get(area, 1.0)
    # Bounded mapping: STARTUP(1.5)->15, COLLEGE/INTERNSHIP(1.0)->10, PERSONAL(0.7)->7.
    # Urgent deadlines always outrank strategic weighting (spec §4/§25).
    return weight * 10.0


def _goal_alignment(db: Session, task: Task) -> float:
    if not task.goal_id:
        return 0.0
    goal: Goal | None = db.query(Goal).filter(Goal.id == task.goal_id).first()
    if goal is None or goal.status not in (GoalStatus.ACTIVE.value, GoalStatus.BEHIND.value):
        return 0.0
    bonus = GOAL_ALIGNMENT_SCORE
    if goal.target_value and goal.progress_fraction >= 0.8:
        bonus += GOAL_NEAR_COMPLETION_BONUS
    return bonus


def score_task(
    db: Session,
    task: Task,
    *,
    available_minutes: int | None = None,
    current_energy: str | None = None,
    now: datetime | None = None,
) -> PriorityBreakdown:
    """Compute the deterministic priority breakdown for one open task."""
    now = now or utcnow()
    bd = PriorityBreakdown()

    bd.deadline_score, note = _deadline_score(task, now)
    if note == "overdue":
        bd.overdue_penalty = OVERDUE_PENALTY
        bd.notes.append("Overdue")
    elif note:
        bd.notes.append(note)

    bd.priority_score = PRIORITY_SCORES.get(task.priority, 0)
    bd.strategic_score = _strategic_score(task.area)

    if task.area == LifeArea.STARTUP.value:
        bd.notes.append("Startup (strategic)")
    alignment = _goal_alignment(db, task)
    bd.goal_alignment_score = alignment
    if alignment >= GOAL_ALIGNMENT_SCORE:
        bd.notes.append("Linked to active goal")

    if available_minutes is not None and task.estimated_duration:
        if task.estimated_duration <= available_minutes:
            bd.effort_fit_score = EFFORT_FIT_BONUS
            bd.notes.append(f"Fits {available_minutes}m window")
        else:
            bd.effort_fit_score = EFFORT_MISFIT_PENALTY

    if task.status == TaskStatus.IN_PROGRESS.value:
        bd.in_progress_boost = IN_PROGRESS_BOOST

    if current_energy and task.energy_level:
        if task.energy_level == current_energy:
            bd.energy_fit_score = ENERGY_FIT_BONUS
        elif (
            current_energy == EnergyLevel.LOW_ENERGY.value
            and task.energy_level == EnergyLevel.DEEP_WORK.value
        ):
            bd.energy_fit_score = -ENERGY_FIT_BONUS

    bd.total = round(
        clamp(
            bd.deadline_score
            + bd.priority_score
            + bd.strategic_score
            + bd.goal_alignment_score
            + bd.overdue_penalty
            + bd.effort_fit_score
            + bd.in_progress_boost
            + bd.energy_fit_score,
            0,
            100,
        ),
        2,
    )
    return bd


def rank_tasks(
    db: Session,
    tasks: list[Task],
    *,
    available_minutes: int | None = None,
    current_energy: str | None = None,
    now: datetime | None = None,
) -> list[tuple[Task, PriorityBreakdown]]:
    scored = [
        (
            t,
            score_task(
                db,
                t,
                available_minutes=available_minutes,
                current_energy=current_energy,
                now=now,
            ),
        )
        for t in tasks
    ]
    scored.sort(key=lambda pair: pair[1].total, reverse=True)
    return scored


def breakdown_to_dict(bd: PriorityBreakdown) -> dict:
    d = asdict(bd)
    d.pop("notes", None)
    return d
