"""Analytics response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class AreaMinutes(BaseModel):
    COLLEGE: float = 0
    INTERNSHIP: float = 0
    STARTUP: float = 0
    PERSONAL: float = 0


class TimeAnalytics(BaseModel):
    period: str
    start: datetime
    end: datetime
    focused_minutes: AreaMinutes  # from focus sessions (actual work)
    scheduled_minutes: AreaMinutes  # from focus-type time blocks (planned)
    total_focused_minutes: float = 0


class ProductivityAnalytics(BaseModel):
    period: str
    start: datetime
    end: datetime
    tasks_completed: int = 0
    tasks_created: int = 0
    tasks_overdue_open: int = 0
    completion_rate: float = 0.0
    planned_minutes: float = 0.0
    actual_minutes: float = 0.0
    average_task_duration_minutes: float = 0.0
    focus_sessions_count: int = 0
    focus_minutes: float = 0.0


class StartupPipelineCounts(BaseModel):
    leads_total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)


class OutreachTotals(BaseModel):
    total: int = 0
    sent: int = 0
    replies: int = 0
    meetings_booked: int = 0
    conversions: int = 0
    reply_rate: float = 0.0
    meeting_rate: float = 0.0
    conversion_rate: float = 0.0


class StartupAnalytics(BaseModel):
    startup_id: int
    startup_name: str
    pipeline: StartupPipelineCounts
    outreach: OutreachTotals
    active_goals: int = 0
    goals_behind: list[str] = []
    running_experiments: int = 0
    customers: int = 0


class WeeklyTrendPoint(BaseModel):
    week_start: date
    outreach_sent: int = 0
    replies: int = 0
    meetings: int = 0
    conversions: int = 0
    new_leads: int = 0


class StartupTrends(BaseModel):
    startup_id: int
    weeks: list[WeeklyTrendPoint]
