"""Task schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import EnergyLevel, LifeArea, TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    area: LifeArea = LifeArea.PERSONAL
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    deadline: datetime | None = None
    estimated_duration: int | None = Field(None, gt=0, le=24 * 60)  # minutes
    actual_duration: int | None = Field(None, ge=0, le=24 * 60)
    energy_level: EnergyLevel | None = None
    goal_id: int | None = None
    project_id: int | None = None


class TaskCreate(TaskBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Contact 20 prospects",
                "area": "STARTUP",
                "priority": "HIGH",
                "deadline": "2026-08-25T18:00:00",
                "estimated_duration": 90,
                "energy_level": "NORMAL",
                "goal_id": 3,
            }
        }
    )


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    area: LifeArea | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    deadline: datetime | None = None
    estimated_duration: int | None = Field(None, gt=0, le=24 * 60)
    actual_duration: int | None = Field(None, ge=0, le=24 * 60)
    energy_level: EnergyLevel | None = None
    goal_id: int | None = None
    project_id: int | None = None

    @field_validator("title")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Title cannot be blank")
        return v


class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    is_overdue: bool = False


class TaskCompleteIn(BaseModel):
    actual_duration: int | None = Field(
        None, ge=0, le=24 * 60, description="Minutes actually spent"
    )


class TaskPriorityBreakdown(BaseModel):
    deadline_score: float = 0
    priority_score: float = 0
    strategic_score: float = 0
    goal_alignment_score: float = 0
    overdue_penalty: float = 0
    effort_fit_score: float = 0
    total: float = 0


class RankedTask(BaseModel):
    """Task enriched with deterministic priority scoring."""

    task: TaskOut
    score: float
    breakdown: TaskPriorityBreakdown
