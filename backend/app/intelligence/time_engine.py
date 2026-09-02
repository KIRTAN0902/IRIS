"""Time intelligence engine.

Calculates free intervals and available time windows, integrating calendar events,
active time blocks, and user routine constraints.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.constraint_engine import (
    evaluate_constraints,
)
from app.services.time_engine import (
    compute_availability,
)
from app.utils.datetime import to_local, utcnow


def calculate_decision_window(
    db: Session,
    user_id: int,
    user_facts: dict[str, Any] | None,
    user_timezone: str,
    *,
    requested_minutes: int | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> tuple[int, list[dict[str, Any]], Any]:
    """Calculate the effective available minutes and free intervals for decision making.

    Considers:
    1. Explicit window or requested minutes if provided.
    2. Scheduled calendar events and time blocks.
    3. Hard routine and sleep constraints.
    """
    now = utcnow()
    now_local = to_local(now, user_timezone)

    constraint_eval = evaluate_constraints(user_facts, now_local)

    start = window_start or now
    end = window_end or (start + timedelta(hours=4))

    avail = compute_availability(db, user_id, window_start=start, window_end=end)
    free_minutes = avail.total_free_minutes

    if requested_minutes is not None:
        effective_minutes = requested_minutes
    elif free_minutes > 0:
        effective_minutes = free_minutes
    else:
        effective_minutes = constraint_eval.minutes_until_next_constraint or 60

    # Ensure hard constraints (sleep / routine) bound the available minutes
    mins_left = constraint_eval.minutes_until_next_constraint
    if mins_left is not None and mins_left > 0:
        effective_minutes = min(effective_minutes, mins_left)

    intervals = [
        {"start": i.start.isoformat(), "end": i.end.isoformat(), "minutes": i.minutes}
        for i in avail.free_intervals
    ]

    return max(1, effective_minutes), intervals, constraint_eval
