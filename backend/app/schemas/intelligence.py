"""Pydantic schemas for Intelligence, Signals, Attention, Decisions, and Feedback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ScheduleBlockType


class RecurringScheduleIn(BaseModel):
    name: str = Field(..., max_length=255)
    type: str = Field(default=ScheduleBlockType.FIXED.value)
    days_of_week: str = Field(default="Mon,Tue,Wed,Thu,Fri,Sat,Sun")
    start_time: str = Field(..., max_length=10, description="HH:MM format, e.g. '06:00'")
    end_time: str = Field(..., max_length=10, description="HH:MM format, e.g. '07:30'")
    is_hard_constraint: bool = Field(default=True)
    status: str = Field(default="ACTIVE")
    extra_data: dict[str, Any] | None = Field(default=None)


class RecurringScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    type: str | None = None
    days_of_week: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    is_hard_constraint: bool | None = None
    status: str | None = None
    extra_data: dict[str, Any] | None = None


class RecurringScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    type: str
    days_of_week: str
    start_time: str
    end_time: str
    is_hard_constraint: bool
    status: str
    extra_data: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CurrentWindowInfo(BaseModel):
    is_in_flexible_window: bool
    is_in_hard_constraint: bool
    active_block_name: str | None = None
    active_block_type: str | None = None
    minutes_remaining_in_block: int | None = None
    minutes_until_next_hard_constraint: int | None = None
    next_hard_constraint_name: str | None = None


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    domain: str
    signal_type: str
    source: str
    provenance: str
    importance: float
    urgency: float
    title: str
    summary: str | None = None
    payload: dict[str, Any] | None = None
    timestamp: datetime
    expires_at: datetime | None = None
    is_active: bool = True


class AttentionItemOut(BaseModel):
    id: str
    type: str
    domain: str
    title: str
    description: str
    score: float
    urgency: float
    impact: float
    provenance: str
    deadline: datetime | None = None
    suggested_action: str | None = None
    source_id: int | str | None = None


class DecisionHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    task_id: int | None = None
    recommendation_type: str
    decision_type: str
    title: str
    reason: str | None = None
    expected_outcome: str | None = None
    duration_minutes: int | None = None
    confidence: float | None = None
    source: str
    opportunity_cost: str | None = None
    evidence: list[str] | None = None
    feedback: str | None = None
    feedback_notes: str | None = None
    feedback_at: datetime | None = None
    created_at: datetime


class DecisionFeedbackIn(BaseModel):
    recommendation_id: int
    feedback: str = Field(
        ...,
        description="ACCEPTED | REJECTED | DEFERRED | COMPLETED | PARTIALLY_COMPLETED",
    )
    notes: str | None = None


class DecisionFeedbackOut(BaseModel):
    id: int
    recommendation_id: int
    feedback: str
    feedback_notes: str | None = None
    feedback_at: datetime
    message: str


class TodayStateOut(BaseModel):
    date: str
    current_time: str
    user_timezone: str
    available_minutes_today: int
    current_window: CurrentWindowInfo
    fixed_commitments: list[dict[str, Any]]
    flexible_windows: list[dict[str, Any]]
    urgent_obligations: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    goals: list[dict[str, Any]]
    startup: dict[str, Any] | None = None
    current_recommendation: dict[str, Any] | None = None
    attention_items: list[dict[str, Any]] = Field(default_factory=list)
    domain_signals: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    recent_decisions: list[dict[str, Any]] = Field(default_factory=list)
