"""Routines: tick-offs, streaks and the "today" view shared by the API, IRIS's tools and situation."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.habit import Habit, HabitLog
from app.models.user import User
from app.schemas.habit import HabitCreate, HabitDay, HabitOut, HabitUpdate
from app.utils.datetime import to_local, utcnow

# How far back streaks are counted.
MAX_LOOKBACK_DAYS = 400


def today_for(user: User) -> date:
    return to_local(utcnow(), user.timezone).date()


def _get(db: Session, user: User, habit_id: int) -> Habit:
    habit = db.query(Habit).filter(Habit.id == habit_id, Habit.user_id == user.id).first()
    if habit is None:
        raise NotFoundError("Routine not found.")
    return habit


def find(db: Session, user: User, name: str) -> Habit | None:
    """Match a routine by name, case-insensitively (exact, then prefix, then substring)."""
    needle = name.strip().lower()
    habits = db.query(Habit).filter(Habit.user_id == user.id).all()
    for test in (lambda h: h.name.lower() == needle, lambda h: h.name.lower().startswith(needle), lambda h: needle in h.name.lower()):
        hit = [h for h in habits if test(h)]
        if hit:
            return hit[0]
    return None


def _done_days(db: Session, habit: Habit, since: date) -> set[date]:
    rows = db.query(HabitLog.day).filter(HabitLog.habit_id == habit.id, HabitLog.day >= since).all()
    return {r[0] for r in rows}


def streaks(habit: Habit, done: set[date], today: date) -> tuple[int, int]:
    """(current, best). Only scheduled days count; today only breaks a streak once it's over."""
    start = max(today - timedelta(days=MAX_LOOKBACK_DAYS), habit.created_at.date() if habit.created_at else today)
    start = min(start, min(done, default=start))

    current = 0
    day = today if today in done or not habit.scheduled_on(today) else today - timedelta(days=1)
    while day >= start:
        if habit.scheduled_on(day):
            if day not in done:
                break
            current += 1
        day -= timedelta(days=1)

    best = run = 0
    day = start
    while day <= today:
        if habit.scheduled_on(day):
            if day in done:
                run += 1
                best = max(best, run)
            elif day < today:
                run = 0
        day += timedelta(days=1)
    return current, max(best, current)


def to_out(db: Session, habit: Habit, today: date) -> HabitOut:
    done = _done_days(db, habit, today - timedelta(days=MAX_LOOKBACK_DAYS))
    current, best = streaks(habit, done, today)
    return HabitOut(
        id=habit.id,
        name=habit.name,
        days_of_week=habit.days_of_week,
        time=habit.time,
        duration_min=habit.duration_min,
        description=habit.description,
        active=habit.active,
        position=habit.position,
        scheduled_today=habit.scheduled_on(today),
        done_today=today in done,
        streak=current,
        best_streak=best,
        last_7=[
            HabitDay(day=d, scheduled=habit.scheduled_on(d), done=d in done)
            for d in (today - timedelta(days=i) for i in range(6, -1, -1))
        ],
    )


def list_habits(db: Session, user: User, *, include_inactive: bool = True) -> list[HabitOut]:
    today = today_for(user)
    q = db.query(Habit).filter(Habit.user_id == user.id)
    if not include_inactive:
        q = q.filter(Habit.active.is_(True))
    habits = q.all()
    habits.sort(key=lambda h: (not h.active, h.time is None, h.time or "", h.position, h.id))
    return [to_out(db, h, today) for h in habits]


def create(db: Session, user: User, data: HabitCreate) -> HabitOut:
    count = db.query(Habit).filter(Habit.user_id == user.id).count()
    habit = Habit(user_id=user.id, position=count, **data.model_dump())
    db.add(habit)
    db.commit()
    db.refresh(habit)
    return to_out(db, habit, today_for(user))


def update(db: Session, user: User, habit_id: int, data: HabitUpdate) -> HabitOut:
    habit = _get(db, user, habit_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None and key in {"name", "days_of_week", "active", "position"}:
            continue
        setattr(habit, key, value)
    db.commit()
    db.refresh(habit)
    return to_out(db, habit, today_for(user))


def delete(db: Session, user: User, habit_id: int) -> None:
    db.delete(_get(db, user, habit_id))
    db.commit()


def check(db: Session, user: User, habit_id: int, *, done: bool = True, day: date | None = None) -> HabitOut:
    """Mark a routine done (or not done) for a day; idempotent."""
    habit = _get(db, user, habit_id)
    day = day or today_for(user)
    existing = db.query(HabitLog).filter(HabitLog.habit_id == habit.id, HabitLog.day == day).first()
    if done and existing is None:
        db.add(HabitLog(habit_id=habit.id, user_id=user.id, day=day))
        try:
            db.commit()
        except IntegrityError:  # a double tap raced us; already logged
            db.rollback()
    elif not done and existing is not None:
        db.delete(existing)
        db.commit()
    return to_out(db, habit, today_for(user))


def situation_brief(db: Session, user: User) -> list[dict] | None:
    """Today's routines for IRIS's live situation (None when the user has none)."""
    habits = [h for h in list_habits(db, user, include_inactive=False) if h.scheduled_today]
    if not habits:
        return None
    return [
        {"id": h.id, "name": h.name, "time": h.time, "duration": h.duration_min, "done": h.done_today,
         "streak": h.streak, "description": h.description}
        for h in habits
    ]


def render_brief(brief: list[dict] | None) -> list[str]:
    if not brief:
        return []
    done = sum(1 for h in brief if h["done"])
    lines = [f"\nROUTINES TODAY ({done}/{len(brief)} done):"]
    for h in brief:
        mark = "done" if h["done"] else "not yet"
        when = f" {h['time']}" if h["time"] else ""
        if h["time"] and h.get("duration"):
            when += f" ({h['duration']}m)"
        streak = f", {h['streak']}-day streak" if h["streak"] else ""
        what = f" - {h['description'][:160]}" if h.get("description") else ""
        lines.append(f"- #{h['id']} {h['name']}{when}: {mark}{streak}{what}")
    return lines
