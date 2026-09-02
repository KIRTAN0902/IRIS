"""Experiment schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExperimentStatus


class ExperimentBase(BaseModel):
    startup_id: int
    name: str = Field(..., min_length=1, max_length=255)
    hypothesis: str | None = None
    action: str | None = None
    target: str | None = Field(None, max_length=255)
    metric: str | None = Field(None, max_length=120)


class ExperimentCreate(ExperimentBase):
    status: ExperimentStatus = ExperimentStatus.PLANNED
    started_at: datetime | None = None


class ExperimentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    hypothesis: str | None = None
    action: str | None = None
    target: str | None = None
    metric: str | None = None
    result: str | None = None
    conclusion: str | None = None
    next_action: str | None = None
    status: ExperimentStatus | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ExperimentOut(ExperimentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    result: str | None
    conclusion: str | None
    next_action: str | None
    status: ExperimentStatus
    started_at: datetime | None
    ended_at: datetime | None
