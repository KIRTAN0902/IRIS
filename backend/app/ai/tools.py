"""Read-only AI tool layer.

These functions are the sanctioned way for AI features to access user data:
context_builder composes them into structured context; Gemini never queries
the database itself (spec §29/§37).

Write tools (create_task, log_outreach, ...) are intentionally NOT exposed.
They will be added behind explicit, auditable application-level authorization
when needed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.task import Task
from app.services import analytics_service, time_engine
from app.utils.datetime import localize_date_boundaries, minutes_between, utcnow


def get_today_tasks(db: Session, user) -> list[dict]:
    day_start, day_end = localize_date_boundaries(utcnow().date(), user.timezone)
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.created_at < day_end)
        .order_by(Task.deadline.asc().nulls_last())
        .all()
    )
    return [
        {
            "id": t.id,
            "title": t.title,
            "area": t.area,
            "status": t.status,
            "priority": t.priority,
            "deadline_utc": t.deadline.isoformat() if t.deadline else None,
        }
        for t in tasks
    ]


def get_upcoming_deadlines(db: Session, user, *, limit: int = 10) -> list[dict]:
    now = utcnow()
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.deadline.is_not(None),
            Task.status.in_(["TODO", "IN_PROGRESS"]),
        )
        .order_by(Task.deadline.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id,
            "title": t.title,
            "area": t.area,
            "deadline_utc": t.deadline.isoformat(),
            "minutes_until_deadline": minutes_between(now, t.deadline),
        }
        for t in tasks
    ]


def get_available_time(db: Session, user, *, hours_ahead: int = 12) -> dict:
    from datetime import timedelta

    now = utcnow()
    avail = time_engine.compute_availability(
        db,
        user.id,
        window_start=now,
        window_end=now + timedelta(hours=hours_ahead),
    )
    return {"total_free_minutes": avail.total_free_minutes}


def get_active_goals(db: Session, user) -> list[dict]:
    from app.services.goal_service import active_goals as _active_goals

    return [
        {
            "id": g.id,
            "name": g.name,
            "area": g.area,
            "progress_fraction": round(g.progress_fraction, 3),
            "target": g.target_value,
            "current": g.current_value,
            "unit": g.unit,
        }
        for g in _active_goals(db, user.id)
    ]


def get_startup_metrics(db: Session, user) -> dict | None:
    try:
        return analytics_service.startup_analytics(db, user.id).model_dump()
    except Exception:
        return None


def get_weekly_progress(db: Session, user) -> dict:
    return analytics_service.productivity_analytics(
        db, user.id, period="week", tz_name=user.timezone
    ).model_dump()


READ_TOOLS = {
    "get_today_tasks": get_today_tasks,
    "get_upcoming_deadlines": get_upcoming_deadlines,
    "get_available_time": get_available_time,
    "get_active_goals": get_active_goals,
    "get_startup_metrics": get_startup_metrics,
    "get_weekly_progress": get_weekly_progress,
}

# Write tools are gated off (spec §37). To enable one later it must be added to
# WRITE_TOOLS explicitly AND the calling route must pass an explicit
# allow_write=True authorization flag. Not used anywhere by default.
WRITE_TOOLS: dict[str, ...] = {}
