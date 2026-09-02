"""Startup schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GoalStatus, LifeArea, StartupStatus


class StartupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    current_objective: str | None = None
    status: StartupStatus = StartupStatus.BUILDING


class StartupCreate(StartupBase):
    pass


class StartupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    current_objective: str | None = None
    status: StartupStatus | None = None


class StartupOut(StartupBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


# --- Startup goals reuse the hierarchical Goal model (area=STARTUP) ----------


class StartupGoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    parent_goal_id: int | None = None
    target_value: float | None = Field(None, ge=0)
    current_value: float = Field(0, ge=0)
    unit: str | None = Field(None, max_length=50)
    deadline: datetime | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    area: LifeArea = LifeArea.STARTUP


class StartupGoalUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    parent_goal_id: int | None = None
    target_value: float | None = Field(None, ge=0)
    current_value: float | None = Field(None, ge=0)
    unit: str | None = None
    deadline: datetime | None = None
    status: GoalStatus | None = None
