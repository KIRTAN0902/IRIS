"""Diary tools: IRIS can write, read, search, update, and organize notes and ideas in the user's Diary."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.tools.actions import make_tool
from app.agent.tools.base import Tool
from app.schemas.diary import DiaryEntryCreate, DiaryEntryUpdate
from app.services import diary_service


class _SearchDiaryParams(BaseModel):
    query: str | None = Field(None, description="Keywords to search in title or body content")
    category: str | None = Field(None, description="Filter by category: NOTE, IDEA, REFLECTION, JOURNAL, MEETING, LEARNING, or None for all")
    tag: str | None = Field(None, description="Filter by a specific tag, e.g. 'startup' or 'ai'")
    limit: int = Field(10, description="Max number of entries to return (default 10)")


class _DiaryIdParams(BaseModel):
    entry_id: int = Field(..., description="The ID of the diary entry")


class _CreateDiaryParams(BaseModel):
    title: str = Field(..., description="Short title or headline for the note/idea (e.g. 'Autonomous Coding Idea')")
    content: str = Field(default="", description="The detailed content, thought, meeting notes, reflection, or markdown body")
    category: str = Field(default="NOTE", description="Category: 'NOTE', 'IDEA', 'REFLECTION', 'JOURNAL', 'MEETING', or 'LEARNING'")
    tags: list[str] = Field(default_factory=list, description="Tags for grouping, e.g. ['startup', 'ai']")
    is_pinned: bool = Field(default=False, description="Whether to pin this entry to the top")
    mood: str | None = Field(default=None, description="Optional mood or vibe, e.g. 'inspired', 'focused', 'reflective'")


class _UpdateDiaryParams(BaseModel):
    entry_id: int = Field(..., description="The ID of the diary entry to update")
    title: str | None = Field(None, description="New title if updating")
    content: str | None = Field(None, description="Updated or appended content")
    category: str | None = Field(None, description="New category if updating")
    tags: list[str] | None = Field(None, description="Updated list of tags")
    is_pinned: bool | None = Field(None, description="Pin or unpin the note")
    mood: str | None = Field(None, description="Updated mood")


def _create(db, user, **p):
    create_dto = DiaryEntryCreate(**p)
    entry = diary_service.create_diary_entry(db, user.id, create_dto)
    cat_name = (entry.category or "note").lower()
    return entry, f"Saved {cat_name} in Diary: '{entry.title}' (ID #{entry.id})"


def _read(db, user, query=None, category=None, tag=None, limit=10):
    entries = diary_service.list_diary_entries(
        db,
        user.id,
        search=query,
        category=category,
        tag=tag,
        limit=limit,
    )
    cat_str = f" in category {category}" if category else ""
    query_str = f" matching '{query}'" if query else ""
    return entries, f"Found {len(entries)} diary entries{cat_str}{query_str}."


def _get(db, user, entry_id):
    entry = diary_service.get_diary_entry(db, user.id, entry_id)
    return entry, f"Diary entry #{entry.id}: '{entry.title}'"


def _update(db, user, entry_id, **p):
    update_dto = DiaryEntryUpdate(**p)
    entry = diary_service.update_diary_entry(db, user.id, entry_id, update_dto)
    return entry, f"Updated diary entry #{entry.id}: '{entry.title}'"


def _delete(db, user, entry_id):
    diary_service.delete_diary_entry(db, user.id, entry_id)
    return {"deleted": entry_id}, f"Deleted diary entry #{entry_id}"


def diary_tools() -> list[Tool]:
    return [
        make_tool(
            name="create_diary_entry",
            description="Write a new note, idea, reflection, meeting note, or personal journal entry to the user's Diary notebook. Use this whenever the user asks to save an idea, write in diary, take a note, or record reflections.",
            params=_CreateDiaryParams,
            run=_create,
            read_only=False,
        ),
        make_tool(
            name="read_diary_entries",
            description="Read, search, or list entries from the user's Diary notebook. Supports keyword search across title & content, and filtering by category (NOTE, IDEA, REFLECTION, JOURNAL, MEETING, LEARNING) or tag.",
            params=_SearchDiaryParams,
            run=_read,
            read_only=True,
        ),
        make_tool(
            name="get_diary_entry",
            description="Retrieve the full content and details of a specific diary note by its ID.",
            params=_DiaryIdParams,
            run=_get,
            read_only=True,
        ),
        make_tool(
            name="update_diary_entry",
            description="Update an existing diary entry's title, content, category, tags, or pin status.",
            params=_UpdateDiaryParams,
            run=_update,
            read_only=False,
        ),
        make_tool(
            name="delete_diary_entry",
            description="Delete a diary entry from the user's Diary notebook by its ID.",
            params=_DiaryIdParams,
            run=_delete,
            read_only=False,
            destructive=True,
        ),
    ]
