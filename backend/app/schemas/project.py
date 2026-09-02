"""Project schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LifeArea, ProjectStatus


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    area: LifeArea = LifeArea.PERSONAL
    status: ProjectStatus = ProjectStatus.PLANNED
    deadline: datetime | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    area: LifeArea | None = None
    status: ProjectStatus | None = None
    deadline: datetime | None = None


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    task_count: int = 0
    created_at: datetime
    updated_at: datetime
