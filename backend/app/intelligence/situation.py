"""Situational awareness: IRIS's contextual (working) memory.

Rebuilt from live data on every turn so it is never stale: what is happening
now, today's schedule, what is pending and how it is prioritised, what got
done, goal progress, and what changed since the user last talked to IRIS.

``build_situation`` returns a JSON-serialisable dict (for tools and the API);
``render_situation`` turns it into a compact prompt block sized to the model's
context budget.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.ai_conversation import AIConversation, AIMessage
from app.models.calendar_event import CalendarEvent
from app.models.enums import AIRole, TaskStatus
from app.models.recurring_schedule import RecurringSchedule
from app.models.task import Task
from app.models.time_block import TimeBlock
from app.models.user import User
from app.services import finance_service, habit_service
from app.utils.datetime import localize_date_boundaries, to_local, utcnow

Detail = Literal["compact", "standard", "full"]

_LIST_LIMITS: dict[str, int] = {"compact": 4, "standard": 8, "full": 15}
_OPEN = (TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value, TaskStatus.BLOCKED.value)
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def detail_for_context_window(context_window: int) -> Detail:
    if context_window <= 16_384:
        return "compact"
    if context_window <= 65_536:
        return "standard"
    return "full"


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _due_label(deadline: datetime | None, now_utc: datetime, tz: str) -> str | None:
    if deadline is None:
        return None
    local = to_local(deadline, tz)
    now_local = to_local(now_utc, tz)
    if deadline < now_utc:
        overdue = now_utc - deadline
        if overdue.days >= 1:
            return f"overdue by {overdue.days}d"
        return f"overdue by {max(1, int(overdue.total_seconds() // 3600))}h"
    if local.date() == now_local.date():
        return f"due today {local:%H:%M}"
    if local.date() == (now_local + timedelta(days=1)).date():
        return f"due tomorrow {local:%H:%M}"
    if (local.date() - now_local.date()).days < 7:
        return f"due {local:%a %H:%M}"
    return f"due {local:%d %b}"


def _task_brief(t: Task, now_utc: datetime, tz: str) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "area": t.area,
        "priority": t.priority,
        "status": t.status,
        "due": _due_label(t.deadline, now_utc, tz),
        "estimated_minutes": t.estimated_duration,
    }


def last_user_message_at(db: Session, user_id: int) -> datetime | None:
    row = (
        db.query(AIMessage.created_at)
        .join(AIConversation, AIConversation.id == AIMessage.conversation_id)
        .filter(AIConversation.user_id == user_id, AIMessage.role == AIRole.USER.value)
        .order_by(AIMessage.created_at.desc())
        .first()
    )
    return row[0] if row else None


def _today_schedule(
    db: Session, user: User, now_utc: datetime, now_local: datetime
) -> list[dict[str, Any]]:
    tz = user.timezone
    day_start, day_end = localize_date_boundaries(now_local.date(), tz)
    weekday = _WEEKDAYS[now_local.weekday()]
    now_hm = f"{now_local:%H:%M}"
    items: list[dict[str, Any]] = []

    def status_for(start: str, end: str) -> str:
        if end <= now_hm and end > start:
            return "done"
        if start <= now_hm < end or (end < start and (now_hm >= start or now_hm < end)):
            return "now"
        return "upcoming"

    for s in (
        db.query(RecurringSchedule)
        .filter(RecurringSchedule.user_id == user.id, RecurringSchedule.status == "ACTIVE")
        .all()
    ):
        days = [d.strip()[:3].title() for d in (s.days_of_week or "").split(",") if d.strip()]
        if days and weekday not in days:
            continue
        items.append(
            {
                "start": s.start_time,
                "end": s.end_time,
                "title": s.name,
                "kind": "routine",
                "hard": bool(s.is_hard_constraint),
                "status": status_for(s.start_time, s.end_time),
            }
        )

    for b in (
        db.query(TimeBlock)
        .filter(
            TimeBlock.user_id == user.id,
            TimeBlock.start_time < day_end,
            TimeBlock.end_time > day_start,
            TimeBlock.status != "CANCELLED",
        )
        .all()
    ):
        start, end = f"{to_local(b.start_time, tz):%H:%M}", f"{to_local(b.end_time, tz):%H:%M}"
        title = b.task.title if getattr(b, "task", None) else (b.notes or b.type.title())
        items.append(
            {
                "start": start,
                "end": end,
                "title": title,
                "kind": f"block:{b.type}",
                "hard": b.type == "MEETING",
                "status": "done" if b.status == "DONE" else status_for(start, end),
            }
        )

    for e in (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user.id,
            CalendarEvent.start_time < day_end,
            CalendarEvent.end_time > day_start,
        )
        .all()
    ):
        start, end = f"{to_local(e.start_time, tz):%H:%M}", f"{to_local(e.end_time, tz):%H:%M}"
        items.append(
            {
                "start": start,
                "end": end,
                "title": e.title,
                "kind": "event",
                "hard": True,
                "status": status_for(start, end),
            }
        )

    items.sort(key=lambda i: i["start"])
    return items


def build_situation(
    db: Session,
    user: User,
    context: dict[str, Any] | None = None,
    *,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Snapshot of the user's current situation.

    ``context`` is the decision context from ``build_decision_context``; it is
    reused for ranking and availability so nothing is computed twice.
    ``since`` (UTC) enables the "since we last talked" section.
    """
    if context is None:
        from app.intelligence.context import build_decision_context

        context = build_decision_context(db, user)

    tz = user.timezone
    now_utc = utcnow()
    now_local = to_local(now_utc, tz)
    window = context.get("current_window", {}) or {}

    # --- Tasks ---------------------------------------------------------------
    open_tasks = db.query(Task).filter(Task.user_id == user.id, Task.status.in_(_OPEN)).all()
    today_end = localize_date_boundaries(now_local.date(), tz)[1]
    week_end = now_utc + timedelta(days=7)

    def by_deadline(ts: list[Task]) -> list[Task]:
        return sorted(ts, key=lambda t: t.deadline or datetime.max)

    overdue = by_deadline([t for t in open_tasks if t.deadline and t.deadline < now_utc])
    due_today = by_deadline(
        [t for t in open_tasks if t.deadline and now_utc <= t.deadline < today_end]
    )
    due_soon = by_deadline(
        [t for t in open_tasks if t.deadline and today_end <= t.deadline < week_end]
    )
    in_progress = [t for t in open_tasks if t.status == TaskStatus.IN_PROGRESS.value]
    blocked = [t for t in open_tasks if t.status == TaskStatus.BLOCKED.value]

    top_priorities = []
    for item in context.get("ranked_tasks", []) or []:
        task = item.get("task", {})
        notes = (item.get("breakdown") or {}).get("notes") or []
        top_priorities.append(
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "area": task.get("area"),
                "priority": task.get("priority"),
                "score": round(item.get("priority_score") or 0, 1),
                "why": notes[0] if notes else None,
            }
        )

    # --- Done ------------------------------------------------------------------
    today_start = localize_date_boundaries(now_local.date(), tz)[0]
    done_week = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.status == TaskStatus.COMPLETED.value,
            Task.completed_at.isnot(None),
            Task.completed_at >= now_utc - timedelta(days=7),
        )
        .order_by(Task.completed_at.desc())
        .all()
    )
    done_today = [t for t in done_week if t.completed_at >= today_start]

    # --- Since last conversation ----------------------------------------------------
    since_section = None
    if since is not None and since < now_utc:
        completed_since = [t.title for t in done_week if t.completed_at > since]
        created_since = (
            db.query(Task.title)
            .filter(Task.user_id == user.id, Task.created_at > since)
            .order_by(Task.created_at.desc())
            .limit(10)
            .all()
        )
        became_overdue = [t.title for t in overdue if t.deadline and t.deadline > since]
        gap_hours = (now_utc - since).total_seconds() / 3600
        since_section = {
            "last_talked": to_local(since, tz).strftime("%a %d %b %H:%M"),
            "hours_ago": round(gap_hours, 1),
            "completed": completed_since,
            "created": [r[0] for r in created_since],
            "became_overdue": became_overdue,
        }

    goals = [
        {
            "name": g.get("name"),
            "area": g.get("area"),
            "status": g.get("status"),
            "progress_pct": round((g.get("progress_fraction") or 0) * 100),
        }
        for g in (context.get("goals", {}) or {}).get("all_active_goals", [])
    ]

    now_hm = f"{now_local:%H:%M}"
    next_flexible = next(
        (
            w
            for w in context.get("flexible_windows", []) or []
            if w.get("end", "") > now_hm or w.get("end", "") < w.get("start", "")
        ),
        None,
    )

    brief = lambda ts: [_task_brief(t, now_utc, tz) for t in ts]  # noqa: E731
    return {
        "now": {
            "local_time": now_local.strftime("%A %d %b %Y, %H:%M"),
            "timezone": tz,
            "part_of_day": _part_of_day(now_local.hour),
            "current_block": window.get("active_block_name"),
            "in_hard_commitment": bool(window.get("is_in_hard_constraint")),
            "minutes_left_in_block": window.get("minutes_remaining_in_block"),
            "next_flexible_window": (
                f"{next_flexible['name']} {next_flexible['start']}-{next_flexible['end']}"
                if next_flexible
                else None
            ),
            "next_commitment": window.get("next_hard_constraint_name"),
            "minutes_until_next_commitment": window.get("minutes_until_next_hard_constraint"),
            "free_minutes": context.get("available_minutes"),
            "sleep_time": (context.get("fixed_constraints") or {}).get("hard_sleep_time"),
        },
        "today_schedule": _today_schedule(db, user, now_utc, now_local),
        "tasks": {
            "open_count": len(open_tasks),
            "open_by_area": dict(Counter(t.area for t in open_tasks)),
            "in_progress": brief(in_progress),
            "overdue": brief(overdue),
            "due_today": brief(due_today),
            "due_this_week": brief(due_soon),
            "blocked": brief(blocked),
            "top_priorities": top_priorities,
        },
        "done": {
            "today": [
                {"title": t.title, "area": t.area, "at": f"{to_local(t.completed_at, tz):%H:%M}"}
                for t in done_today
            ],
            "last_7_days_count": len(done_week),
            "last_7_days_by_area": dict(Counter(t.area for t in done_week)),
            "recent": [
                {"title": t.title, "area": t.area, "on": f"{to_local(t.completed_at, tz):%a}"}
                for t in done_week[:10]
            ],
        },
        "goals": goals,
        "money": finance_service.situation_brief(db, user),
        "routines": habit_service.situation_brief(db, user),
        "since_last_conversation": since_section,
    }


# --- Rendering -------------------------------------------------------------------


def _fmt_task(t: dict[str, Any]) -> str:
    bits = [f"#{t['id']} {t['title']}", f"[{t['area']}/{t['priority']}]"]
    if t.get("due"):
        bits.append(t["due"])
    if t.get("estimated_minutes"):
        bits.append(f"~{t['estimated_minutes']}m")
    return " ".join(bits)


def render_situation(s: dict[str, Any], detail: Detail = "standard") -> str:
    n = _LIST_LIMITS[detail]
    now, tasks, done = s["now"], s["tasks"], s["done"]
    lines = ["RIGHT NOW (live situation; recomputed every turn):"]

    clock = f"- {now['local_time']} ({now['part_of_day']}, {now['timezone']})"
    lines.append(clock)
    if now.get("current_block"):
        busy = (
            " - BUSY: hard commitment, not free for other work"
            if now.get("in_hard_commitment")
            else ""
        )
        lines.append(
            f"- In: {now['current_block']} ({now.get('minutes_left_in_block') or 0}m left){busy}"
        )
    if now.get("next_commitment"):
        lines.append(
            f"- Next commitment: {now['next_commitment']} in "
            f"{now.get('minutes_until_next_commitment') or 0}m"
        )
    if now.get("in_hard_commitment"):
        if now.get("next_flexible_window"):
            lines.append(f"- Next free window: {now['next_flexible_window']}")
    elif now.get("free_minutes") is not None:
        lines.append(f"- Usable free time now: {now['free_minutes']}m")
    if now.get("sleep_time"):
        lines.append(f"- Hard sleep time: {now['sleep_time']}")

    since = s.get("since_last_conversation")
    if since and (since["completed"] or since["created"] or since["became_overdue"]):
        lines.append(
            f"\nSINCE YOU LAST TALKED ({since['last_talked']}, {since['hours_ago']}h ago):"
        )
        if since["completed"]:
            lines.append(f"- Completed: {', '.join(since['completed'][:n])}")
        if since["created"]:
            lines.append(f"- Added: {', '.join(since['created'][:n])}")
        if since["became_overdue"]:
            lines.append(f"- Became overdue: {', '.join(since['became_overdue'][:n])}")

    if s["today_schedule"]:
        lines.append("\nTODAY'S SCHEDULE:")
        for i in s["today_schedule"][: n + 4]:
            hard = " [hard]" if i["hard"] else ""
            lines.append(f"- {i['start']}-{i['end']} {i['title']}{hard} ({i['status']})")

    by_area = ", ".join(f"{k} {v}" for k, v in sorted(tasks["open_by_area"].items()))
    lines.append(f"\nTASKS ({tasks['open_count']} open{': ' + by_area if by_area else ''}):")
    for label, key in (
        ("In progress", "in_progress"),
        ("OVERDUE", "overdue"),
        ("Due today", "due_today"),
        ("Due this week", "due_this_week"),
        ("Blocked", "blocked"),
    ):
        items = tasks[key]
        if items:
            lines.append(f"{label}:")
            lines.extend(f"  - {_fmt_task(t)}" for t in items[:n])
            if len(items) > n:
                lines.append(f"  - ...and {len(items) - n} more (use get_tasks)")
    if tasks["top_priorities"]:
        lines.append("Priority ranking (IRIS deterministic engine, highest first):")
        for i, t in enumerate(tasks["top_priorities"][:n], 1):
            why = f" - {t['why']}" if t.get("why") else ""
            lines.append(f"  {i}. #{t['id']} {t['title']} [{t['area']}/{t['priority']}]{why}")
    if not tasks["open_count"]:
        lines.append("- No open tasks.")

    lines.append(
        f"\nDONE: {len(done['today'])} today, {done['last_7_days_count']} in the last 7 days"
        + (
            " ("
            + ", ".join(f"{k} {v}" for k, v in sorted(done["last_7_days_by_area"].items()))
            + ")"
            if done["last_7_days_by_area"]
            else ""
        )
    )
    for t in done["today"][:n]:
        lines.append(f"  - {t['at']} {t['title']} [{t['area']}]")

    if s["goals"]:
        lines.append("\nGOALS:")
        for g in s["goals"][:n]:
            lines.append(f"- {g['name']} [{g['area']}] {g['progress_pct']}% ({g['status']})")

    lines.extend(habit_service.render_brief(s.get("routines")))
    lines.extend(finance_service.render_brief(s.get("money")))

    return "\n".join(lines)
