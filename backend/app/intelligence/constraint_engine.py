"""Constraint engine -- hard vs soft constraint evaluation.

Separates non-negotiable hard constraints (sleep, fixed internship hours, routine,
calendar events, hard deadlines) from soft preferences (strategic focus, deep work).
Gemini and the decision engine must NEVER violate hard constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from app.models.enums import ScheduleBlockType


@dataclass
class RoutineBlock:
    name: str
    start_time: str  # "HH:MM" 24-hr format
    end_time: str  # "HH:MM" 24-hr format
    type: str = ScheduleBlockType.FIXED.value
    is_hard_constraint: bool = True
    days: list[str] = field(
        default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    )


# Default structured user routine if not specified in database or user.facts
DEFAULT_ROUTINE_BLOCKS: list[RoutineBlock] = [
    RoutineBlock("Yoga", "06:00", "07:30", ScheduleBlockType.PERSONAL.value, True),
    RoutineBlock("Bath", "07:30", "08:00", ScheduleBlockType.PERSONAL.value, True),
    RoutineBlock("Puja", "08:00", "08:30", ScheduleBlockType.PERSONAL.value, True),
    RoutineBlock("Breakfast", "08:30", "09:00", ScheduleBlockType.PERSONAL.value, True),
    RoutineBlock(
        "Morning Flexible Window", "09:00", "10:30", ScheduleBlockType.FLEXIBLE.value, False
    ),
    RoutineBlock("Buffer", "10:30", "11:00", ScheduleBlockType.BUFFER.value, False),
    RoutineBlock(
        "Internship",
        "11:00",
        "20:00",
        ScheduleBlockType.WORK.value,
        True,
        ["Mon", "Tue", "Wed", "Thu", "Fri"],
    ),
    RoutineBlock("Dinner", "20:00", "21:00", ScheduleBlockType.PERSONAL.value, True),
    RoutineBlock(
        "Night Flexible Window", "21:00", "23:00", ScheduleBlockType.FLEXIBLE.value, False
    ),
]

DEFAULT_SLEEP_TIME = "23:00"
DEFAULT_WAKE_TIME = "06:00"


@dataclass
class ConstraintEvaluation:
    current_time_local: str
    is_in_hard_constraint: bool
    active_constraint_name: str | None
    minutes_until_next_constraint: int | None
    next_constraint_name: str | None
    hard_sleep_time: str
    hard_wake_time: str
    fixed_commitments: list[dict[str, Any]]
    flexible_windows: list[dict[str, Any]]
    active_block_type: str | None = None
    is_in_flexible_window: bool = False
    minutes_remaining_in_block: int | None = None


def parse_hhmm(s: str) -> time:
    parts = s.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def get_user_routine(
    facts: dict[str, Any] | None,
    recurring_schedules: list[Any] | None = None,
) -> list[RoutineBlock]:
    """Extract routine blocks from recurring schedule models or user facts."""
    if recurring_schedules:
        blocks: list[RoutineBlock] = []
        for sched in recurring_schedules:
            days = [d.strip() for d in sched.days_of_week.split(",") if d.strip()]
            blocks.append(
                RoutineBlock(
                    name=sched.name,
                    start_time=sched.start_time,
                    end_time=sched.end_time,
                    type=sched.type,
                    is_hard_constraint=sched.is_hard_constraint,
                    days=days,
                )
            )
        if blocks:
            return blocks

    if not facts or "routine" not in facts:
        return DEFAULT_ROUTINE_BLOCKS

    blocks = []
    for item in facts.get("routine", []):
        blocks.append(
            RoutineBlock(
                name=item.get("name", "Commitment"),
                start_time=item.get("start", "00:00"),
                end_time=item.get("end", "00:00"),
                type=item.get("type", ScheduleBlockType.FIXED.value),
                is_hard_constraint=item.get("is_hard", item.get("is_hard_constraint", True)),
                days=item.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
            )
        )
    return blocks or DEFAULT_ROUTINE_BLOCKS


def evaluate_constraints(
    facts: dict[str, Any] | None,
    current_local_dt: datetime,
    calendar_events: list[Any] | None = None,
    recurring_schedules: list[Any] | None = None,
) -> ConstraintEvaluation:
    """Evaluate position relative to routine constraints, flexible windows, and sleep."""
    routine = get_user_routine(facts, recurring_schedules=recurring_schedules)
    sleep_str = (facts or {}).get("sleep", DEFAULT_SLEEP_TIME)
    wake_str = (facts or {}).get("wake", DEFAULT_WAKE_TIME)

    current_t = current_local_dt.time()
    day_abbr = current_local_dt.strftime("%a")
    now_minutes = current_t.hour * 60 + current_t.minute

    active_constraint: str | None = None
    active_block_type: str | None = None
    is_in_constraint = False
    is_in_flexible = False
    minutes_remaining_in_block: int | None = None

    # 1. Check sleep window (typically 23:00 to 06:00)
    sleep_t = parse_hhmm(sleep_str)
    wake_t = parse_hhmm(wake_str)
    sleep_minutes = sleep_t.hour * 60 + sleep_t.minute
    wake_minutes = wake_t.hour * 60 + wake_t.minute

    if sleep_t > wake_t:
        # Crosses midnight (e.g. 23:00 - 06:00)
        if current_t >= sleep_t or current_t < wake_t:
            is_in_constraint = True
            active_constraint = "Sleep"
            active_block_type = ScheduleBlockType.SLEEP.value
            if current_t >= sleep_t:
                minutes_remaining_in_block = (24 * 60 - now_minutes) + wake_minutes
            else:
                minutes_remaining_in_block = wake_minutes - now_minutes
    else:
        if sleep_t <= current_t < wake_t:
            is_in_constraint = True
            active_constraint = "Sleep"
            active_block_type = ScheduleBlockType.SLEEP.value
            minutes_remaining_in_block = wake_minutes - now_minutes

    # 2. Check routine blocks for today
    today_blocks = [b for b in routine if day_abbr in b.days]
    fixed_commitments = []
    flexible_windows = []

    for b in today_blocks:
        b_start = parse_hhmm(b.start_time)
        b_end = parse_hhmm(b.end_time)
        b_end_min = b_end.hour * 60 + b_end.minute

        block_dict = {
            "name": b.name,
            "start": b.start_time,
            "end": b.end_time,
            "type": b.type,
            "is_hard": b.is_hard_constraint,
        }

        if b.type == ScheduleBlockType.FLEXIBLE.value:
            flexible_windows.append(block_dict)
        elif b.is_hard_constraint or b.type in (
            ScheduleBlockType.FIXED.value,
            ScheduleBlockType.WORK.value,
            ScheduleBlockType.PERSONAL.value,
            ScheduleBlockType.SLEEP.value,
            ScheduleBlockType.UNAVAILABLE.value,
        ):
            fixed_commitments.append(block_dict)

        # Check if currently inside this block
        if b_start <= current_t < b_end:
            if b.is_hard_constraint:
                if not is_in_constraint:
                    is_in_constraint = True
                    active_constraint = b.name
                    active_block_type = b.type
                    minutes_remaining_in_block = b_end_min - now_minutes
            elif b.type == ScheduleBlockType.FLEXIBLE.value:
                is_in_flexible = True
                if not active_constraint:
                    active_constraint = b.name
                    active_block_type = b.type
                    minutes_remaining_in_block = b_end_min - now_minutes

    # If flexible windows weren't defined in routine, use default flexible slots
    if not flexible_windows:
        flexible_windows = [
            {
                "name": "Morning flexible window",
                "start": "09:00",
                "end": "10:30",
                "type": "FLEXIBLE",
            },
            {
                "name": "Night flexible window",
                "start": "21:00",
                "end": "23:00",
                "type": "FLEXIBLE",
            },
        ]

    # 3. Calculate minutes until next hard constraint
    next_constraint_name: str | None = None
    minutes_until_next: int | None = None

    upcoming = []
    for b in today_blocks:
        if not b.is_hard_constraint and b.type == ScheduleBlockType.FLEXIBLE.value:
            continue
        b_start = parse_hhmm(b.start_time)
        b_min = b_start.hour * 60 + b_start.minute
        if b_min > now_minutes:
            upcoming.append((b_min - now_minutes, b.name))

    # Sleep constraint
    if sleep_minutes > now_minutes:
        upcoming.append((sleep_minutes - now_minutes, f"Sleep ({sleep_str})"))
    else:
        upcoming.append(((24 * 60 - now_minutes) + sleep_minutes, f"Sleep ({sleep_str})"))

    if upcoming:
        upcoming.sort(key=lambda x: x[0])
        minutes_until_next, next_constraint_name = upcoming[0]

    return ConstraintEvaluation(
        current_time_local=current_local_dt.strftime("%H:%M"),
        is_in_hard_constraint=is_in_constraint,
        active_constraint_name=active_constraint,
        active_block_type=active_block_type,
        is_in_flexible_window=is_in_flexible,
        minutes_remaining_in_block=minutes_remaining_in_block,
        minutes_until_next_constraint=minutes_until_next,
        next_constraint_name=next_constraint_name,
        hard_sleep_time=sleep_str,
        hard_wake_time=wake_str,
        fixed_commitments=fixed_commitments,
        flexible_windows=flexible_windows,
    )


def sanitize_duration_against_constraints(
    duration_minutes: int | None,
    evaluation: ConstraintEvaluation,
    max_available_minutes: int | None = None,
) -> int | None:
    """Ensure recommended duration does not violate hard constraints (e.g. sleep or routine)."""
    if duration_minutes is None:
        return None

    duration = max(1, duration_minutes)

    # 1. Respect explicit max available minutes if provided
    if max_available_minutes is not None and max_available_minutes > 0:
        duration = min(duration, max_available_minutes)

    # 2. Hard constraint clamp: minutes until next hard constraint (e.g. sleep at 23:00)
    if evaluation.minutes_until_next_constraint is not None:
        if evaluation.minutes_until_next_constraint <= 0:
            return None
        duration = min(duration, evaluation.minutes_until_next_constraint)

    return max(1, duration)
