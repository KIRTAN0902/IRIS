"""Workout plan schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.schemas.habit import DAY_NAMES


def _clean_days(v: str | list[str] | None) -> str | None:
    """Like routines, but an empty value is allowed (a plan not tied to a weekday)."""
    if v is None:
        return v
    parts = v.split(",") if isinstance(v, str) else v
    picked = {p.strip()[:3].title() for p in parts if p.strip()}
    unknown = picked - set(DAY_NAMES)
    if unknown:
        raise ValueError(f"Unknown day(s): {', '.join(sorted(unknown))}. Use Mon..Sun.")
    return ",".join(d for d in DAY_NAMES if d in picked)


def _blank_to_none(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return None if v in {"", "-", "—", "–"} else v


class ExerciseIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    sets_reps: str | None = Field(None, max_length=40, description='e.g. "4x5-8"')
    time: str | None = Field(None, max_length=40)
    muscles: str | None = Field(None, max_length=160)
    weight: str | None = Field(None, max_length=40, description='e.g. "7.5x2" or "20"')
    notes: str | None = Field(None, max_length=255)

    _blank = field_validator("sets_reps", "time", "muscles", "weight", "notes", mode="before")(_blank_to_none)


class ExerciseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    sets_reps: str | None = Field(None, max_length=40)
    time: str | None = Field(None, max_length=40)
    muscles: str | None = Field(None, max_length=160)
    weight: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=255)

    _blank = field_validator("sets_reps", "time", "muscles", "weight", "notes", mode="before")(_blank_to_none)


class WorkoutIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    focus: str | None = Field(None, max_length=160)
    days_of_week: str = Field("", description='Days it is for, e.g. "Sun" or "Mon,Thu"')
    duration: str | None = Field(None, max_length=40, description='e.g. "75-85 min"')
    notes: str | None = None
    exercises: list[ExerciseIn] = Field(default_factory=list, max_length=60)

    _days = field_validator("days_of_week", mode="before")(_clean_days)
    _blank = field_validator("focus", "duration", "notes", mode="before")(_blank_to_none)


class WorkoutPatch(BaseModel):
    """Partial update; ``exercises`` (when given) replaces the whole list."""

    name: str | None = Field(None, min_length=1, max_length=80)
    focus: str | None = Field(None, max_length=160)
    days_of_week: str | None = None
    duration: str | None = Field(None, max_length=40)
    notes: str | None = None
    exercises: list[ExerciseIn] | None = Field(None, max_length=60)

    _days = field_validator("days_of_week", mode="before")(_clean_days)
    _blank = field_validator("focus", "duration", "notes", mode="before")(_blank_to_none)


class ExerciseOut(BaseModel):
    id: int
    position: int
    name: str
    sets_reps: str | None
    time: str | None
    muscles: str | None
    weight: str | None
    notes: str | None
    done_today: bool = False


class WorkoutOut(BaseModel):
    id: int
    name: str
    focus: str | None
    days_of_week: str
    duration: str | None
    notes: str | None
    is_today: bool
    exercises: list[ExerciseOut]
    done_count: int
    last_done_on: date | None


class ExerciseCheck(BaseModel):
    done: bool = True
    day: date | None = None
