"""Routine tools: IRIS can add routines and tick them off by chat or voice ("done with gym")."""

from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, Field

from app.agent.tools.actions import _with_id, make_tool
from app.agent.tools.base import Tool
from app.core.errors import NotFoundError
from app.schemas.habit import HabitCreate, HabitUpdate
from app.services import habit_service


class _CheckParams(BaseModel):
    habit_id: int | None = Field(None, description="Routine id (from get_routines or the situation)")
    name: str | None = Field(None, description="Or the routine's name, e.g. 'gym'")
    done: bool = Field(True, description="False to undo")
    day: Date | None = Field(None, description="Local date; default today")


class _HabitId(BaseModel):
    habit_id: int


def _resolve(db, user, habit_id, name):
    if habit_id:
        return habit_id
    habit = habit_service.find(db, user, name or "")
    if habit is None:
        raise NotFoundError(f"No routine called '{name}'. Create it first with create_routine.")
    return habit.id


def _routines(db, user):
    habits = habit_service.list_habits(db, user)
    today = [h for h in habits if h.active and h.scheduled_today]
    return habits, f"{sum(h.done_today for h in today)}/{len(today)} routines done today"


def _create(db, user, **p):
    h = habit_service.create(db, user, HabitCreate(**p))
    when = f" at {h.time}" if h.time else ""
    return h, f"Added routine #{h.id}: {h.name} ({h.days_of_week}{when})"


def _update(db, user, habit_id, **p):
    h = habit_service.update(db, user, habit_id, HabitUpdate(**p))
    return h, f"Updated routine #{h.id}: {h.name}"


def _check(db, user, habit_id=None, name=None, done=True, day=None):
    h = habit_service.check(db, user, _resolve(db, user, habit_id, name), done=done, day=day)
    if not done:
        return h, f"Unmarked {h.name}"
    streak = f" ({h.streak}-day streak)" if h.streak > 1 else ""
    return h, f"{h.name} done{streak}"


def _delete(db, user, habit_id):
    habit_service.delete(db, user, habit_id)
    return {"deleted": habit_id}, f"Deleted routine #{habit_id}"


def habit_tools() -> list[Tool]:
    return [
        make_tool(
            name="get_routines",
            description="The user's daily routines (gym, yoga...) with today's status, streaks and last 7 days.",
            run=_routines,
            read_only=True,
        ),
        make_tool(
            name="check_routine",
            description="Mark a routine done (or undone with done=false) for today or a given day. Use when the user says they did it.",
            params=_CheckParams,
            run=_check,
            read_only=False,
        ),
        make_tool(
            name="create_routine",
            description='Add a routine to track daily, e.g. name "Gym", days_of_week "Mon,Wed,Fri", time "18:30".',
            params=HabitCreate,
            run=_create,
            read_only=False,
        ),
        make_tool(
            name="update_routine",
            description="Change a routine's name, days, time, or pause it (active=false).",
            params=_with_id(HabitUpdate, "habit_id", "routine"),
            run=_update,
            read_only=False,
        ),
        make_tool(
            name="delete_routine",
            description="Delete a routine and its history.",
            params=_HabitId,
            run=_delete,
            read_only=False,
            destructive=True,
        ),
    ]
