"""Workout tools: IRIS can save plans (e.g. pasted from Notion), read today's, and update weights."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.tools.actions import _with_id, make_tool
from app.agent.tools.base import Tool
from app.core.errors import NotFoundError
from app.schemas.workout import ExerciseUpdate, WorkoutIn, WorkoutPatch
from app.services import workout_service as ws


class _Which(BaseModel):
    workout_id: int | None = Field(None, description="Workout id")
    workout: str | None = Field(None, description="Or its name, e.g. 'CST'")


class _GetParams(BaseModel):
    today_only: bool = Field(False, description="Only today's workout(s)")


class _ExerciseEdit(_Which, ExerciseUpdate):
    exercise: str = Field(..., description="Exercise name to change, e.g. 'bench press'")


class _ExerciseCheck(_Which):
    exercises: list[str] = Field(..., min_length=1, description="Exercise names to mark")
    done: bool = True


def _resolve(db, user, workout_id, workout):
    if workout_id:
        return workout_id
    w = ws.find(db, user, workout or "")
    if w is None:
        raise NotFoundError(f"No workout called '{workout}'.")
    return w.id


def _get(db, user, today_only=False):
    plans = ws.todays(db, user) if today_only else ws.list_workouts(db, user)
    names = ", ".join(f"{w.name} ({w.days_of_week or 'any day'})" for w in plans)
    return plans, (f"{len(plans)} workout(s): {names}" if plans else "No workouts saved")


def _save(db, user, **p):
    w = ws.create(db, user, WorkoutIn(**p))
    return w, f"Saved workout #{w.id}: {w.name} with {len(w.exercises)} exercises ({w.days_of_week or 'any day'})"


def _update(db, user, workout_id, **p):
    w = ws.update(db, user, workout_id, WorkoutPatch(**p))
    return w, f"Updated workout #{w.id}: {w.name}"


def _edit_exercise(db, user, exercise, workout_id=None, workout=None, **p):
    wid = _resolve(db, user, workout_id, workout)
    plan = next(w for w in ws.list_workouts(db, user) if w.id == wid)
    ex = ws.find_exercise(plan, exercise)
    if ex is None:
        raise NotFoundError(f"No exercise like '{exercise}' in {plan.name}.")
    w = ws.update_exercise(db, user, wid, ex.id, ExerciseUpdate(**p))
    changed = ", ".join(f"{k} {v}" for k, v in p.items())
    return w, f"{ex.name}: {changed}"


def _check(db, user, exercises, workout_id=None, workout=None, done=True):
    wid = _resolve(db, user, workout_id, workout) if (workout_id or workout) else None
    if wid is None:
        today = ws.todays(db, user)
        if not today:
            raise NotFoundError("No workout is planned for today; say which workout.")
        wid = today[0].id
    plan = next(w for w in ws.list_workouts(db, user) if w.id == wid)
    marked, missing = [], []
    for name in exercises:
        ex = ws.find_exercise(plan, name)
        if ex is None:
            missing.append(name)
            continue
        plan = ws.check(db, user, wid, ex.id, done=done)
        marked.append(ex.name)
    note = f"; not found: {', '.join(missing)}" if missing else ""
    return plan, f"{plan.name}: {plan.done_count}/{len(plan.exercises)} done{note}"


def _delete(db, user, workout_id):
    ws.delete(db, user, workout_id)
    return {"deleted": workout_id}, f"Deleted workout #{workout_id}"


def workout_tools() -> list[Tool]:
    return [
        make_tool(
            name="get_workouts",
            description="The user's gym workout plans (exercises, sets x reps, weights, muscles), with today's ticks.",
            params=_GetParams,
            run=_get,
            read_only=True,
        ),
        make_tool(
            name="save_workout",
            description=(
                "Save a new workout plan, e.g. from a table the user pasted (Notion etc.): name like 'CST', focus "
                "'Chest, Shoulders, Triceps', days_of_week 'Sun', duration '75-85 min', and every exercise with "
                "sets_reps, time, muscles, weight exactly as written. Use update_workout to change an existing one."
            ),
            params=WorkoutIn,
            run=_save,
            read_only=False,
        ),
        make_tool(
            name="update_workout",
            description="Change a workout's details; passing exercises replaces the whole exercise list.",
            params=_with_id(WorkoutPatch, "workout_id", "workout"),
            run=_update,
            read_only=False,
        ),
        make_tool(
            name="update_exercise",
            description="Change one exercise in a workout by name, e.g. new weight '10x2' or sets_reps '4x6'.",
            params=_ExerciseEdit,
            run=_edit_exercise,
            read_only=False,
        ),
        make_tool(
            name="check_exercises",
            description="Mark exercises done (or undone) in today's workout, by name.",
            params=_ExerciseCheck,
            run=_check,
            read_only=False,
        ),
        make_tool(
            name="delete_workout",
            description="Delete a workout plan.",
            params=_with_id(BaseModel, "workout_id", "workout"),
            run=_delete,
            read_only=False,
            destructive=True,
        ),
    ]
