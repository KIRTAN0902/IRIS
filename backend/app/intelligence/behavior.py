"""Behaviour model: how the user actually follows through, learned from their data.

Looks at the last few weeks of deadlines, routines, workouts, money and use of
IRIS, and turns them into (1) measured patterns with sample sizes and (2)
guidance for how IRIS should adapt. A pattern only appears once there is
enough evidence, so the picture sharpens gradually as history builds up.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.models.ai_conversation import AIConversation, AIMessage
from app.models.enums import AIRole, TaskStatus, TransactionKind
from app.models.finance import FinanceTransaction
from app.models.habit import Habit, HabitLog
from app.models.task import Task
from app.models.user import User
from app.models.workout import Workout, WorkoutLog
from app.utils.datetime import from_local, to_local, utcnow

WINDOW_DAYS = 28
_HALF = WINDOW_DAYS // 2
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Minimum evidence before a pattern is reported.
MIN_DEADLINES = 5
MIN_ROUTINE_DAYS = 5
MIN_WEEKDAY_SAMPLES = 3
MIN_WORKOUT_DAYS = 3
MIN_TRANSACTIONS = 8


def _pct(part: int | float, whole: int | float) -> int:
    return round(100 * part / whole) if whole else 0


def _trend(recent: tuple[int, int], prior: tuple[int, int], min_each: int) -> dict[str, Any] | None:
    """Compare success rates (done, total) of the recent half-window with the one before."""
    (r_done, r_total), (p_done, p_total) = recent, prior
    if r_total < min_each or p_total < min_each:
        return None
    r, p = _pct(r_done, r_total), _pct(p_done, p_total)
    direction = "improving" if r - p >= 10 else "slipping" if p - r >= 10 else "steady"
    return {"recent_pct": r, "prior_pct": p, "direction": direction}


def _humanize_hours(hours: float) -> str:
    if hours < 24:
        return f"{max(1, round(hours))}h"
    days = hours / 24
    return f"{days:.1f} days" if days < 10 else f"{round(days)} days"


# --- Deadlines ---------------------------------------------------------------------------


def deadlines(db: Session, user: User, today: date) -> dict[str, Any] | None:
    now = utcnow()
    since = from_local(today - timedelta(days=WINDOW_DAYS), user.timezone)
    split = from_local(today - timedelta(days=_HALF), user.timezone)
    due = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.deadline.isnot(None), Task.deadline >= since, Task.deadline < now)
        .all()
    )
    if len(due) < MIN_DEADLINES:
        return {"samples": len(due), "enough": False}

    outcome: dict[int, str] = {}
    delays: list[float] = []
    for t in due:
        if t.status == TaskStatus.COMPLETED.value and t.completed_at:
            if t.completed_at <= t.deadline:
                outcome[t.id] = "on_time"
            else:
                outcome[t.id] = "late"
                delays.append((t.completed_at - t.deadline).total_seconds() / 3600)
        elif t.status == TaskStatus.CANCELLED.value:
            outcome[t.id] = "dropped"
        else:
            outcome[t.id] = "missed"

    counts = Counter(outcome.values())
    slips = Counter(t.area for t in due if outcome[t.id] in {"late", "missed"})
    area, n = slips.most_common(1)[0] if slips else (None, 0)

    def half(lo: datetime, hi: datetime) -> tuple[int, int]:
        part = [t for t in due if lo <= t.deadline < hi]
        return sum(outcome[t.id] == "on_time" for t in part), len(part)

    return {
        "samples": len(due),
        "enough": True,
        "on_time": counts["on_time"],
        "late": counts["late"],
        "missed": counts["missed"],
        "dropped": counts["dropped"],
        "on_time_pct": _pct(counts["on_time"], len(due)),
        "typical_delay": _humanize_hours(median(delays)) if delays else None,
        "slipping_area": area if n >= 2 else None,
        "trend": _trend(half(split, now), half(since, split), 3),
    }


# --- Routines ----------------------------------------------------------------------------


def routines(db: Session, user: User, today: date) -> dict[str, Any] | None:
    habits = db.query(Habit).filter(Habit.user_id == user.id, Habit.active.is_(True)).all()
    if not habits:
        return None
    start = today - timedelta(days=WINDOW_DAYS)
    logs = defaultdict(set)
    for habit_id, day in (
        db.query(HabitLog.habit_id, HabitLog.day).filter(HabitLog.user_id == user.id, HabitLog.day >= start).all()
    ):
        logs[habit_id].add(day)

    per_habit, by_weekday = [], defaultdict(lambda: [0, 0])
    recent, prior = [0, 0], [0, 0]
    total_done = total_sched = 0
    for h in habits:
        created = h.created_at.date() if h.created_at else start
        done = sched = 0
        day = max(start, created)
        while day <= today:
            # Today only counts once it's done: it isn't missed until it's over.
            if h.scheduled_on(day) and (day < today or day in logs[h.id]):
                hit = day in logs[h.id]
                sched += 1
                done += hit
                by_weekday[day.weekday()][0] += hit
                by_weekday[day.weekday()][1] += 1
                bucket = recent if day >= today - timedelta(days=_HALF) else prior
                bucket[0] += hit
                bucket[1] += 1
            day += timedelta(days=1)
        if sched:
            per_habit.append({"name": h.name, "done": done, "scheduled": sched, "pct": _pct(done, sched)})
        total_done += done
        total_sched += sched

    if total_sched < MIN_ROUTINE_DAYS:
        return {"samples": total_sched, "enough": False, "routines": per_habit}

    overall = _pct(total_done, total_sched)
    rated = {d: _pct(v[0], v[1]) for d, v in by_weekday.items() if v[1] >= MIN_WEEKDAY_SAMPLES}
    weakest = min(rated, key=rated.get) if rated else None
    strongest = max(rated, key=rated.get) if rated else None
    per_habit.sort(key=lambda r: r["pct"])
    return {
        "samples": total_sched,
        "enough": True,
        "pct": overall,
        "routines": per_habit,
        "weakest_day": (
            {"day": _WEEKDAYS[weakest], "pct": rated[weakest]} if weakest is not None and rated[weakest] <= overall - 15 else None
        ),
        "strongest_day": {"day": _WEEKDAYS[strongest], "pct": rated[strongest]} if strongest is not None else None,
        "trend": _trend(tuple(recent), tuple(prior), MIN_ROUTINE_DAYS),
    }


# --- Workouts ----------------------------------------------------------------------------


def workouts(db: Session, user: User, today: date) -> dict[str, Any] | None:
    plans = [w for w in db.query(Workout).filter(Workout.user_id == user.id).all() if w.days and w.exercises]
    if not plans:
        return None
    start = today - timedelta(days=WINDOW_DAYS)
    logged = defaultdict(set)
    for wid, ex_id, day in (
        db.query(WorkoutLog.workout_id, WorkoutLog.exercise_id, WorkoutLog.day)
        .filter(WorkoutLog.user_id == user.id, WorkoutLog.day >= start)
        .all()
    ):
        logged[(wid, day)].add(ex_id)

    full = partial = skipped = 0
    for w in plans:
        created = w.created_at.date() if w.created_at else start
        day = max(start, created)
        while day <= today:
            if day.strftime("%a") in w.days and (day < today or logged[(w.id, day)]):
                share = len(logged[(w.id, day)]) / len(w.exercises)
                if share >= 0.8:
                    full += 1
                elif share > 0:
                    partial += 1
                else:
                    skipped += 1
            day += timedelta(days=1)
    total = full + partial + skipped
    if total < MIN_WORKOUT_DAYS:
        return {"samples": total, "enough": False}
    return {
        "samples": total,
        "enough": True,
        "full": full,
        "partial": partial,
        "skipped": skipped,
        "pct": _pct(full + 0.5 * partial, total),
    }


# --- Money -------------------------------------------------------------------------------


def money(db: Session, user: User, today: date) -> dict[str, Any] | None:
    first = today.replace(day=1)
    prev_first = (first - timedelta(days=1)).replace(day=1)
    rows = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.user_id == user.id, FinanceTransaction.occurred_on >= prev_first)
        .all()
    )
    expenses = [t for t in rows if t.kind == TransactionKind.EXPENSE.value]
    if len(expenses) < MIN_TRANSACTIONS:
        return {"samples": len(expenses), "enough": False} if expenses else None

    so_far = sum(float(t.amount) for t in expenses if t.occurred_on >= first)
    same_point = first.replace(day=1) - timedelta(days=1)
    prev_cutoff = prev_first + timedelta(days=min(today.day, same_point.day) - 1)
    prev_so_far = sum(float(t.amount) for t in expenses if prev_first <= t.occurred_on <= prev_cutoff)
    cats = Counter()
    for t in expenses:
        if t.occurred_on >= first:
            cats[t.category] += float(t.amount)
    weekend = [float(t.amount) for t in expenses if t.occurred_on.weekday() >= 5]
    weekday = [float(t.amount) for t in expenses if t.occurred_on.weekday() < 5]
    days_we = max(1, len({t.occurred_on for t in expenses if t.occurred_on.weekday() >= 5}))
    days_wd = max(1, len({t.occurred_on for t in expenses if t.occurred_on.weekday() < 5}))
    return {
        "samples": len(expenses),
        "enough": True,
        "month_so_far": round(so_far),
        "last_month_same_point": round(prev_so_far),
        "change_pct": _pct(so_far - prev_so_far, prev_so_far) if prev_so_far else None,
        "top_category": cats.most_common(1)[0][0] if cats else None,
        "weekend_heavier": sum(weekend) / days_we > 1.4 * (sum(weekday) / days_wd) if weekend and weekday else False,
    }


# --- Engagement --------------------------------------------------------------------------


def engagement(db: Session, user: User, today: date) -> dict[str, Any]:
    start = today - timedelta(days=13)
    tz = user.timezone
    days: set[date] = set()
    since = from_local(start, tz)
    for (ts,) in (
        db.query(AIMessage.created_at)
        .join(AIConversation, AIConversation.id == AIMessage.conversation_id)
        .filter(AIConversation.user_id == user.id, AIMessage.role == AIRole.USER.value, AIMessage.created_at >= since)
        .all()
    ):
        days.add(to_local(ts, tz).date())
    for (ts,) in db.query(Task.completed_at).filter(Task.user_id == user.id, Task.completed_at >= since).all():
        days.add(to_local(ts, tz).date())
    days |= {d for (d,) in db.query(HabitLog.day).filter(HabitLog.user_id == user.id, HabitLog.day >= start).all()}
    days |= {d for (d,) in db.query(WorkoutLog.day).filter(WorkoutLog.user_id == user.id, WorkoutLog.day >= start).all()}
    days |= {
        d for (d,) in db.query(FinanceTransaction.occurred_on).filter(
            FinanceTransaction.user_id == user.id, FinanceTransaction.occurred_on >= start
        ).all()
    }
    return {"active_days": len(days), "of_days": 14}


# --- Assembly ----------------------------------------------------------------------------


def adapt_guidance(b: dict[str, Any]) -> list[dict[str, str]]:
    """How IRIS adjusts to what it has learned: ``iris`` (instruction) and ``you`` (shown to the user)."""
    out: list[dict[str, str]] = []

    def add(iris: str, you: str) -> None:
        out.append({"iris": iris, "you": you})

    d = b.get("deadlines") or {}
    if d.get("enough"):
        if d["on_time_pct"] < 60:
            area = f", especially {d['slipping_area'].lower()} work" if d.get("slipping_area") else ""
            add(
                f"They often miss deadlines ({d['on_time_pct']}% on time{area}). When planning, set an internal "
                "deadline a day or two early, break big tasks into small first steps, and check in before due dates.",
                f"You finish {d['on_time_pct']}% of tasks by their deadline{area}, so IRIS suggests earlier internal "
                "deadlines, smaller first steps and check-ins before things are due.",
            )
        elif d["on_time_pct"] >= 85:
            add(
                f"Reliable with deadlines ({d['on_time_pct']}% on time): ambitious plans are fine.",
                f"You finish {d['on_time_pct']}% of tasks on time, so IRIS can plan ambitiously with you.",
            )
        if d.get("typical_delay") and d.get("late", 0) >= 2:
            add(
                f"When late, it's usually by about {d['typical_delay']}; budget that buffer into plans.",
                f"When something runs late it's usually by about {d['typical_delay']}, so IRIS leaves that much buffer.",
            )
    r = b.get("routines") or {}
    if r.get("enough"):
        if r.get("weakest_day"):
            w = r["weakest_day"]
            add(
                f"{w['day']} is their weakest routine day ({w['pct']}%): keep {w['day']} plans lighter and nudge routines that day.",
                f"{w['day']} is your weakest day for routines ({w['pct']}%), so IRIS keeps {w['day']} lighter and nudges you then.",
            )
        weak = [x for x in r["routines"] if x["scheduled"] >= 4 and x["pct"] < 50]
        if weak:
            names = ", ".join(f"{x['name']} ({x['pct']}%)" for x in weak[:3])
            add(
                f"Struggling with: {names}. Suggest a smaller version or a better time instead of more pressure.",
                f"{names} {'is' if len(weak) == 1 else 'are'} hard to keep up, so IRIS will suggest a smaller version or a better time.",
            )
        if r["pct"] >= 80:
            add(
                f"Very consistent with routines ({r['pct']}%): acknowledge streaks briefly when relevant.",
                f"You keep {r['pct']}% of your routines, and IRIS notices your streaks.",
            )
    w = b.get("workouts") or {}
    if w.get("enough") and w["skipped"] >= max(2, w["samples"] // 3):
        add(
            f"Skips planned workouts fairly often ({w['skipped']} of {w['samples']}): remind them of the plan before gym time.",
            f"You skipped {w['skipped']} of {w['samples']} planned workouts, so IRIS reminds you of the plan before gym time.",
        )
    trends = [x.get("trend") for x in (d, r) if x.get("enough") and x.get("trend")]
    if any(t["direction"] == "slipping" for t in trends):
        add(
            "Follow-through dropped over the last two weeks: be supportive, help them reset with one or two small wins, don't pile on.",
            "Your follow-through dipped over the last two weeks, so IRIS will help you reset with small wins instead of piling on.",
        )
    elif trends and all(t["direction"] == "improving" for t in trends):
        add(
            "Follow-through is improving lately: notice it when relevant.",
            "Your follow-through has been improving over the last two weeks.",
        )
    m = b.get("money") or {}
    if m.get("enough") and m.get("change_pct") is not None and m["change_pct"] >= 25:
        add(
            f"Spending is running {m['change_pct']}% above last month at this point; mention it when money comes up.",
            f"You're spending {m['change_pct']}% more than last month at this point, and IRIS will mention it when money comes up.",
        )
    return out


def observe_behavior(db: Session, user: User) -> dict[str, Any]:
    today = to_local(utcnow(), user.timezone).date()
    b: dict[str, Any] = {
        "window_days": WINDOW_DAYS,
        "deadlines": deadlines(db, user, today),
        "routines": routines(db, user, today),
        "workouts": workouts(db, user, today),
        "money": money(db, user, today),
        "engagement": engagement(db, user, today),
    }
    scores = [
        x["on_time_pct"] if key == "deadlines" else x["pct"]
        for key in ("deadlines", "routines", "workouts")
        if (x := b.get(key)) and x.get("enough")
    ]
    evidence = sum((b.get(k) or {}).get("samples", 0) for k in ("deadlines", "routines", "workouts", "money"))
    b["consistency_score"] = round(sum(scores) / len(scores)) if scores else None
    b["confidence"] = "solid" if evidence >= 60 else "growing" if evidence >= 20 else "early"
    b["evidence"] = evidence
    b["adapt"] = adapt_guidance(b)
    return b


def render_behavior(b: dict[str, Any] | None) -> list[str]:
    if not b:
        return []
    lines = [f"HOW THEY FOLLOW THROUGH (learned from the last {b['window_days']} days; confidence: {b['confidence']}):"]
    if b.get("consistency_score") is not None:
        lines.append(f"- Overall consistency: {b['consistency_score']}/100")
    d = b.get("deadlines") or {}
    if d.get("enough"):
        delay = f"; late ones by ~{d['typical_delay']}" if d.get("typical_delay") else ""
        area = f"; slips most in {d['slipping_area']}" if d.get("slipping_area") else ""
        trend = f"; {d['trend']['direction']} ({d['trend']['prior_pct']}% -> {d['trend']['recent_pct']}%)" if d.get("trend") else ""
        lines.append(
            f"- Deadlines: {d['on_time_pct']}% on time ({d['on_time']} on time, {d['late']} late, {d['missed']} missed of {d['samples']}){delay}{area}{trend}"
        )
    r = b.get("routines") or {}
    if r.get("enough"):
        each = ", ".join(f"{x['name']} {x['pct']}%" for x in sorted(r["routines"], key=lambda x: -x["pct"]))
        weak = f"; weakest day {r['weakest_day']['day']} ({r['weakest_day']['pct']}%)" if r.get("weakest_day") else ""
        trend = f"; {r['trend']['direction']}" if r.get("trend") else ""
        lines.append(f"- Routines: {r['pct']}% done on scheduled days ({each}){weak}{trend}")
    w = b.get("workouts") or {}
    if w.get("enough"):
        lines.append(f"- Workouts: {w['full']} full, {w['partial']} partial, {w['skipped']} skipped of {w['samples']} planned")
    m = b.get("money") or {}
    if m.get("enough"):
        change = f" ({'+' if m['change_pct'] >= 0 else ''}{m['change_pct']}% vs last month at this point)" if m.get("change_pct") is not None else ""
        extra = "; spends more on weekends" if m.get("weekend_heavier") else ""
        lines.append(f"- Money: Rs {m['month_so_far']} spent this month{change}; top category {m['top_category']}{extra}")
    e = b.get("engagement") or {}
    lines.append(f"- Active with IRIS on {e.get('active_days', 0)} of the last {e.get('of_days', 14)} days")
    if len(lines) == 2:
        lines.append("- Still learning: patterns appear once there are a few weeks of tasks, routines and workouts.")
    if b.get("adapt"):
        lines.append("ADAPT TO THEM (quietly; don't lecture or recite these numbers unless asked):")
        lines.extend(f"- {a['iris']}" for a in b["adapt"])
    return lines
