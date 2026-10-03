"""AI Memory schemas for persistent contextual memory."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryCategory = Literal[
    "PREFERENCE",
    "ROUTINE",
    "WORK_STYLE",
    "FACT",
    "PEOPLE",
    "PROJECT",
    "CONSTRAINT",
    "INSTRUCTION",
    "GENERAL",
]

MEMORY_CATEGORY_GUIDE = (
    "PREFERENCE (likes/dislikes, how they want things done), "
    "ROUTINE (day-to-day schedule: wake/sleep, classes, gym, commute, recurring commitments), "
    "WORK_STYLE (how/when they work best: focus length, peak hours, breaks, energy patterns), "
    "FACT (background: college, job, life details), "
    "PEOPLE (co-founders, mentors, teammates, family and their roles), "
    "PROJECT (startup/product/codebase details and status), "
    "CONSTRAINT (hard limits that must never be violated), "
    "INSTRUCTION (standing rules for how IRIS should behave)"
)


class MemoryCreate(BaseModel):
    category: MemoryCategory = "GENERAL"
    key: str | None = Field(None, max_length=120)
    content: str = Field(..., min_length=2, max_length=5000)
    importance: float = Field(0.5, ge=0.0, le=1.0)
    confidence: float = Field(0.9, ge=0.0, le=1.0)
    conversation_id: int | None = None


class MemoryUpdate(BaseModel):
    category: MemoryCategory | None = None
    key: str | None = Field(None, max_length=120)
    content: str | None = Field(None, min_length=2, max_length=5000)
    importance: float | None = Field(None, ge=0.0, le=1.0)
    is_active: bool | None = None


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    conversation_id: int | None
    category: str
    key: str | None
    content: str
    importance: float
    confidence: float
    source: str
    is_active: bool
    access_count: int
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExtractedMemoryItem(BaseModel):
    content: str = Field(..., description="The factual context or preference to remember")
    category: MemoryCategory = Field(
        "GENERAL",
        description="Category: " + MEMORY_CATEGORY_GUIDE,
    )
    key: str | None = Field(None, description="Short unique slug or topic identifier, e.g. 'deep_work_preference'")
    importance: float = Field(0.5, ge=0.0, le=1.0, description="Importance score from 0.0 to 1.0")


class MemoryExtractionResponse(BaseModel):
    memories: list[ExtractedMemoryItem] = Field(
        default_factory=list,
        description="List of salient context items, facts, preferences, or rules learned from the conversation turn to store into long-term memory",
    )
    conversation_summary: str = Field(
        "",
        description=(
            "Updated summary of the WHOLE conversation so far (previous summary + this turn), "
            "3-6 short '- ' bullet lines: what was discussed, decided or planned, and what is "
            "still open. Concrete names, numbers and dates. Max ~80 words."
        ),
    )
    topics: list[str] = Field(
        default_factory=list, description="1-4 short topic tags, e.g. 'startup outreach', 'internship'"
    )
