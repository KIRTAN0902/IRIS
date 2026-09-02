"""Outreach activity schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OutreachResult, OutreachType


class OutreachActivityBase(BaseModel):
    lead_id: int
    startup_id: int
    type: OutreachType = OutreachType.EMAIL
    timestamp: datetime | None = None  # defaults to now server-side
    message: str | None = None
    result: OutreachResult | None = OutreachResult.SENT
    notes: str | None = None


class OutreachActivityCreate(OutreachActivityBase):
    update_lead_status: bool = Field(
        True,
        description="Also advance the lead's status based on this outreach result",
    )


class OutreachActivityUpdate(BaseModel):
    type: OutreachType | None = None
    timestamp: datetime | None = None
    message: str | None = None
    result: OutreachResult | None = None
    notes: str | None = None


class OutreachActivityOut(OutreachActivityBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
