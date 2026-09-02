"""TimeBlock + CalendarEvent schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EventSource, TimeBlockStatus, TimeBlockType


class TimeBlockBase(BaseModel):
    task_id: int | None = None
    start_time: datetime
    end_time: datetime
    type: TimeBlockType = TimeBlockType.FOCUS
    status: TimeBlockStatus = TimeBlockStatus.SCHEDULED
    notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _end_after_start(self) -> TimeBlockBase:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class TimeBlockCreate(TimeBlockBase):
    allow_overlap: bool = Field(
        False, description="Set true to intentionally schedule overlapping blocks"
    )


class TimeBlockUpdate(BaseModel):
    task_id: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    type: TimeBlockType | None = None
    status: TimeBlockStatus | None = None
    notes: str | None = None


class TimeBlockOut(TimeBlockBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    duration_minutes: int
    created_at: datetime


class CalendarEventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    start_time: datetime
    end_time: datetime
    location: str | None = Field(None, max_length=255)
    source: EventSource = EventSource.INTERNAL
    external_id: str | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> CalendarEventBase:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class CalendarEventCreate(CalendarEventBase):
    pass


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None


class CalendarEventOut(CalendarEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    duration_minutes: int
    created_at: datetime
