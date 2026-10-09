"""Routine (habit) schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _clean_days(v: str | list[str] | None) -> str | None:
    """Accept "Mon,Wed" or ["mon", "wed"]; store canonical "Mon,Wed" in week order."""
    if v is None:
        return v
    parts = v.split(",") if isinstance(v, str) else v
    picked = {p.strip()[:3].title() for p in parts if p.strip()}
    unknown = picked - set(DAY_NAMES)
    if unknown:
        raise ValueError(f"Unknown day(s): {', '.join(sorted(unknown))}. Use Mon..Sun.")
    if not picked:
        raise ValueError("Pick at least one day.")
    return ",".join(d for d in DAY_NAMES if d in picked)


def _clean_time(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    try:
        h, m = (int(p) for p in v.strip().split(":")[:2])
    except ValueError as exc:
        raise ValueError("Time must look like 18:30.") from exc
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("Time must look like 18:30.")
    return f"{h:02d}:{m:02d}"


class HabitCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    days_of_week: str = Field("Mon,Tue,Wed,Thu,Fri,Sat,Sun", description='Days it applies, e.g. "Mon,Wed,Fri"')
    time: str | None = Field(None, description='Usual time, "HH:MM" (optional)')
    duration_min: int | None = Field(None, ge=1, le=24 * 60, description="Usual length in minutes")
    description: str | None = Field(None, max_length=2000, description="What to do in this routine")

    _days = field_validator("days_of_week", mode="before")(_clean_days)
    _time = field_validator("time", mode="before")(_clean_time)


class HabitUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    days_of_week: str | None = None
    time: str | None = None
    active: bool | None = None
    position: int | None = None
    duration_min: int | None = Field(None, ge=1, le=24 * 60)
    description: str | None = Field(None, max_length=2000)

    _days = field_validator("days_of_week", mode="before")(_clean_days)
    _time = field_validator("time", mode="before")(_clean_time)


class HabitDay(BaseModel):
    day: date
    scheduled: bool
    done: bool


class HabitOut(BaseModel):
    id: int
    name: str
    days_of_week: str
    time: str | None
    duration_min: int | None
    description: str | None
    active: bool
    position: int
    scheduled_today: bool
    done_today: bool
    streak: int
    best_streak: int
    last_7: list[HabitDay]


class HabitCheck(BaseModel):
    done: bool = True
    day: date | None = Field(None, description="Local date; default today")
