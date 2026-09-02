"""Goal schemas (hierarchical)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GoalStatus, LifeArea


class GoalBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    parent_goal_id: int | None = None
    area: LifeArea = LifeArea.PERSONAL
    deadline: datetime | None = None
    target_value: float | None = Field(None, ge=0)
    current_value: float = Field(0, ge=0)
    unit: str | None = Field(None, max_length=50)
    status: GoalStatus = GoalStatus.ACTIVE


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    parent_goal_id: int | None = None
    area: LifeArea | None = None
    deadline: datetime | None = None
    target_value: float | None = Field(None, ge=0)
    current_value: float | None = Field(None, ge=0)
    unit: str | None = None
    status: GoalStatus | None = None


class GoalOut(GoalBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    progress_fraction: float = 0.0
    created_at: datetime
    updated_at: datetime


class GoalTreeNode(GoalOut):
    """Goal with nested children for tree rendering."""

    children: list[GoalTreeNode] = []
