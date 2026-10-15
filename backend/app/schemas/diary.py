"""Diary schemas for notes, ideas, reflections, and journaling."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DiaryEntryBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(default="")
    category: str = Field(default="NOTE", max_length=32)
    tags: list[str] = Field(default_factory=list)
    is_pinned: bool = Field(default=False)
    mood: str | None = Field(default=None, max_length=32)


class DiaryEntryCreate(DiaryEntryBase):
    pass


class DiaryEntryUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = None
    category: str | None = Field(None, max_length=32)
    tags: list[str] | None = None
    is_pinned: bool | None = None
    mood: str | None = Field(None, max_length=32)


class DiaryEntryOut(DiaryEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class DiaryListResponse(BaseModel):
    items: list[DiaryEntryOut]
    total: int
    categories: list[str]
    all_tags: list[str]
