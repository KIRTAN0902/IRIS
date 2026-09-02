"""Metric + user + focus session + daily review schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AIRole, FocusStatus

# --- Users -------------------------------------------------------------------


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    # Plain str, not EmailStr: the v1 default address lives under a reserved
    # TLD (.local) which strict email validation rejects on OUTPUT.
    email: str
    timezone: str
    facts: dict | None = None
    preferences: dict | None = None
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    timezone: str | None = Field(None, max_length=64)
    facts: dict | None = None
    preferences: dict | None = None

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str | None) -> str | None:
        if v is not None:
            from zoneinfo import ZoneInfo

            try:
                ZoneInfo(v)
            except Exception as exc:
                raise ValueError(f"Unknown timezone: {v}") from exc
        return v


# --- Focus sessions ----------------------------------------------------------


class FocusStartIn(BaseModel):
    task_id: int | None = None
    planned_duration: int | None = Field(None, gt=0, le=24 * 60)
    notes: str | None = Field(None, max_length=1000)


class FocusCompleteIn(BaseModel):
    status: FocusStatus = FocusStatus.COMPLETED
    notes: str | None = None


class FocusSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    task_id: int | None
    started_at: datetime
    ended_at: datetime | None
    planned_duration: int | None
    actual_duration: int | None
    status: FocusStatus
    notes: str | None


# --- Daily reviews -----------------------------------------------------------


class DailyReviewIn(BaseModel):
    date: date
    blockers: str | None = None
    productivity_rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = None


class DailyReviewUpdate(BaseModel):
    completed_tasks: int | None = Field(None, ge=0)
    incomplete_tasks: int | None = Field(None, ge=0)
    blockers: str | None = None
    productivity_rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = None
    ai_summary: str | None = None


class DailyReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date: date
    completed_tasks: int | None
    incomplete_tasks: int | None
    blockers: str | None
    productivity_rating: int | None
    notes: str | None
    ai_summary: str | None
    created_at: datetime
    updated_at: datetime


# --- Metrics -----------------------------------------------------------------


class MetricCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    value: float
    unit: str | None = Field(None, max_length=50)
    source: str | None = Field(None, max_length=120)
    startup_id: int | None = None
    timestamp: datetime | None = None


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    startup_id: int | None
    name: str
    value: float
    unit: str | None
    source: str | None
    timestamp: datetime


# --- AI conversations --------------------------------------------------------


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: AIRole
    content: str
    created_at: datetime
