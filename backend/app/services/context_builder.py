"""AI context builder.

Builds compact, structured context for Gemini. The application decides what
the model sees -- never the whole database (spec §29/§30). Output is plain
JSON-serializable dicts; the AI layer has no SQLAlchemy imports.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import LifeArea, TaskStatus
from app.models.focus_session import FocusSession
from app.models.goal import Goal
from app.models.task import Task
from app.schemas.task import TaskOut
from app.services import analytics_service
from app.services.memory_service import memory_service
from app.services.priority_engine import PriorityBreakdown, breakdown_to_dict
from app.utils.datetime import minutes_between, to_local, utcnow



def _serialize_ranked(pair: tuple[Task, PriorityBreakdown]) -> dict:
    task, breakdown = pair
    return {
        "task": TaskOut.model_validate(task).model_dump(mode="json"),
        "priority_score": breakdown.total,
        "breakdown": {**breakdown_to_dict(breakdown), "notes": breakdown.notes},
    }


def build_recommendation_context(
    db: Session,
    user,
    *,
    available_minutes: int | None = None,
    window_start=None,
    window_end=None,
) -> dict:
    """Context for POST /ai/recommend."""
    from app.intelligence.context import build_decision_context

    return build_decision_context(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
    )


def build_daily_review_context(db: Session, user, *, local_date) -> dict:
    day_start, day_end = _local_day_bounds(local_date, user.timezone)

    completed_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.completed_at >= day_start,
            Task.completed_at < day_end,
        )
        .all()
    )
    missed = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.deadline.is_not(None),
            Task.deadline < day_end,
            Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
        )
        .all()
    )

    focus_rows = (
        db.query(Task.area, FocusSession.actual_duration)
        .outerjoin(Task, FocusSession.task_id == Task.id)
        .filter(
            FocusSession.user_id == user.id,
            FocusSession.started_at >= day_start,
            FocusSession.started_at < day_end,
        )
        .all()
    )
    time_by_area: dict[str, float] = {a.value: 0.0 for a in LifeArea}
    unknown_minutes = 0.0
    for area, minutes in focus_rows:
        m = float(minutes or 0)
        if area in time_by_area:
            time_by_area[area] += m
        else:
            unknown_minutes += m

    from app.models.daily_review import DailyReview

    review_row = (
        db.query(DailyReview)
        .filter(DailyReview.user_id == user.id, DailyReview.date == local_date)
        .first()
    )

    startup_metrics = None
    try:
        startup_metrics = analytics_service.startup_analytics(db, user.id).model_dump()
    except Exception:
        pass

    def task_brief(t: Task) -> dict:
        return {
            "id": t.id,
            "title": t.title,
            "area": t.area,
            "status": t.status,
            "deadline_utc": t.deadline.isoformat() if t.deadline else None,
            "estimated_duration": t.estimated_duration,
            "actual_duration": t.actual_duration,
        }

    return {
        "date": local_date.isoformat(),
        "completed_tasks": [task_brief(t) for t in completed_tasks],
        "missed_or_overdue_tasks": [task_brief(t) for t in missed],
        "time_by_area_minutes": time_by_area,
        "unassigned_focus_minutes": unknown_minutes,
        "user_review": {
            "productivity_rating": review_row.productivity_rating if review_row else None,
            "notes": review_row.notes if review_row else None,
            "blockers": review_row.blockers if review_row else None,
        },
        "startup_metrics": startup_metrics,
    }


def build_startup_analysis_context(db: Session, user, *, startup_id: int | None = None) -> dict:
    metrics = analytics_service.startup_analytics(db, user.id, startup_id).model_dump()
    trends = analytics_service.startup_trends(
        db, user.id, weeks=6, startup_id=startup_id
    ).model_dump()

    from app.models.experiment import Experiment
    from app.models.startup import Startup

    startup = (
        (
            db.query(Startup)
            .filter(Startup.user_id == user.id, Startup.id == (startup_id or Startup.id))
            .first()
        )
        if startup_id
        else db.query(Startup).filter(Startup.user_id == user.id).first()
    )

    experiments = []
    if startup:
        rows = (
            db.query(Experiment)
            .filter(Experiment.startup_id == startup.id)
            .order_by(Experiment.started_at.desc().nulls_last())
            .limit(10)
            .all()
        )
        experiments = [
            {
                "name": e.name,
                "hypothesis": e.hypothesis,
                "metric": e.metric,
                "result": e.result,
                "conclusion": e.conclusion,
                "status": e.status,
            }
            for e in rows
        ]

    # Startup goals live in the shared hierarchical Goal table with area=STARTUP.
    goal_rows = (
        db.query(Goal)
        .filter(Goal.user_id == user.id, Goal.area == LifeArea.STARTUP.value)
        .filter(Goal.status.in_(["ACTIVE", "BEHIND"]))
        .limit(20)
        .all()
    )
    startup_goals = [
        {
            "name": g.name,
            "target": g.target_value,
            "current": g.current_value,
            "unit": g.unit,
            "deadline": g.deadline.isoformat() if g.deadline else None,
            "progress_fraction": round(g.progress_fraction, 3),
        }
        for g in goal_rows
    ]

    return {
        "startup": {
            "name": startup.name,
            "description": startup.description,
            "current_objective": startup.current_objective,
            "status": startup.status,
        }
        if startup
        else None,
        "metrics": metrics,
        "weekly_trends": trends["weeks"],
        "startup_goals": startup_goals,
        "recent_experiments": experiments,
    }


def build_ask_context(db: Session, user, *, question: str) -> dict:
    """Light context for free-form Ask IRIS."""
    now = utcnow()
    upcoming = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.deadline.is_not(None),
            Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
        )
        .order_by(Task.deadline.asc())
        .limit(15)
        .all()
    )
    today_start, today_end = _local_day_bounds(now.date(), user.timezone)
    relevant_statuses = [
        TaskStatus.TODO.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.COMPLETED.value,
    ]
    todays = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.created_at < today_end,
            Task.status.in_(relevant_statuses),
        )
        .limit(settings.ai_context_max_tasks)
        .all()
    )
    productivity_week = analytics_service.productivity_analytics(
        db, user.id, period="week", tz_name=user.timezone
    ).model_dump()
    try:
        startup = analytics_service.startup_analytics(db, user.id).model_dump()
    except Exception:
        startup = None

    memories = memory_service.search_relevant_memories(
        db, user.id, query=question, limit=8, mark_accessed=True
    )
    memories_data = [
        {
            "id": m.id,
            "category": m.category,
            "key": m.key,
            "content": m.content,
            "importance": m.importance,
        }
        for m in memories
    ]

    return {
        "question": question,
        "current_time_utc": now.isoformat(),
        "current_local_time": to_local(now, user.timezone).isoformat(),
        "user_timezone": user.timezone,
        "memories": memories_data,
        "todays_tasks": [
            {"id": t.id, "title": t.title, "area": t.area, "status": t.status} for t in todays
        ],
        "upcoming_deadlines": [
            {
                "id": t.id,
                "title": t.title,
                "area": t.area,
                "deadline_utc": t.deadline.isoformat(),
                "minutes_until_deadline": minutes_between(now, t.deadline),
            }
            for t in upcoming
        ],
        "week_productivity": productivity_week,
        "startup_metrics": startup,
    }



# --- helpers -----------------------------------------------------------------


def _local_day_bounds(day, tz_name: str):
    from app.utils.datetime import localize_date_boundaries

    return localize_date_boundaries(day, tz_name)


def ranked_to_schema(ranked_list) -> list:
    from app.schemas.task import RankedTask, TaskPriorityBreakdown

    return [
        RankedTask(
            task=TaskOut.model_validate(t),
            score=bd.total,
            breakdown=TaskPriorityBreakdown(**breakdown_to_dict(bd)),
        )
        for t, bd in ranked_list
    ]
