"""Lead (CRM) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import LeadStatus


class LeadBase(BaseModel):
    startup_id: int
    name: str = Field(..., min_length=1, max_length=255)
    company: str | None = Field(None, max_length=255)
    role: str | None = Field(None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    website: str | None = Field(None, max_length=255)
    source: str | None = Field(None, max_length=120)
    status: LeadStatus = LeadStatus.LEAD
    notes: str | None = None
    last_contacted: datetime | None = None
    next_follow_up: datetime | None = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    company: str | None = None
    role: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    source: str | None = None
    status: LeadStatus | None = None
    notes: str | None = None
    last_contacted: datetime | None = None
    next_follow_up: datetime | None = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Name cannot be blank")
        return v


class LeadOut(LeadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
