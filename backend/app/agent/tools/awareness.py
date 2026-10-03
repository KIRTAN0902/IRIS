"""Awareness tools: live situation, personal model, and completed-work history."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.intelligence.personal_model import build_personal_model
from app.intelligence.situation import build_situation, last_user_message_at
from app.models.enums import LifeArea, TaskStatus
from app.models.task import Task
from app.models.user import User
from app.utils.datetime import to_local, utcnow

# --- 1. GetSituationTool ---


class GetSituationTool(Tool):
    name = "get_situation"
    description = (
        "Full live snapshot of the user's situation: current time block and next commitment, "
        "today's schedule, in-progress/overdue/due-today/due-this-week/blocked tasks, the "
        "priority ranking, what was completed today and this week, goal progress, and what "
        "changed since the last conversation. Use when the summary in context is not enough."
    )
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        situation = build_situation(db, user, since=last_user_message_at(db, user.id))
        tasks = situation["tasks"]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=situation,
            summary=(
                f"{tasks['open_count']} open tasks, {len(tasks['overdue'])} overdue, "
                f"{len(tasks['due_today'])} due today"
            ),
        )


# --- 2. GetPersonalProfileTool ---


class GetPersonalProfileTool(Tool):
    name = "get_personal_profile"
    description = (
        "The user's personal model: profile facts, operating preferences, weekly routine, "
        "everything they told IRIS about their routine/work style/preferences/rules, and "
        "patterns observed from their behaviour (peak hours, best days, estimation accuracy, "
        "focus-session length, area balance). Use for planning, scheduling and advice."
    )
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        model = build_personal_model(db, user)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=model,
            summary=(
                f"{len(model['stated'])} stated preferences/rules, "
                f"{len(model['observed']) - 1} observed patterns"
            ),
        )


# --- 3. GetCompletedTasksTool ---


class GetCompletedTasksParams(BaseModel):
    days: int = Field(7, ge=1, le=90, description="Look back this many days")
    area: LifeArea | None = Field(None, description="Filter by area")
    limit: int = Field(30, ge=1, le=100, description="Max tasks to return")


class GetCompletedTasksTool(Tool):
    name = "get_completed_tasks"
    description = (
        "List tasks the user completed in the last N days (what got done), newest first, "
        "with completion time and estimated vs actual duration."
    )
    parameters_schema = GetCompletedTasksParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        days = kwargs.get("days", 7)
        query = db.query(Task).filter(
            Task.user_id == user.id,
            Task.status == TaskStatus.COMPLETED.value,
            Task.completed_at.isnot(None),
            Task.completed_at >= utcnow() - timedelta(days=days),
        )
        if kwargs.get("area"):
            query = query.filter(Task.area == kwargs["area"])
        tasks = query.order_by(Task.completed_at.desc()).limit(kwargs.get("limit", 30)).all()
        data = [
            {
                "id": t.id,
                "title": t.title,
                "area": t.area,
                "priority": t.priority,
                "completed_at": to_local(t.completed_at, user.timezone).strftime("%a %d %b %H:%M"),
                "estimated_minutes": t.estimated_duration,
                "actual_minutes": t.actual_duration,
            }
            for t in tasks
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=data,
            summary=f"{len(data)} tasks completed in the last {days} days",
        )


# --- 4. Conversation memory (shared across all conversations) ---


class SearchConversationsParams(BaseModel):
    query: str = Field(..., min_length=2, description="What to look for, e.g. 'startup pricing'")
    limit: int = Field(5, ge=1, le=15)


class SearchConversationsTool(Tool):
    name = "search_conversations"
    description = (
        "Search ALL past conversations with the user (any thread) for a topic. Returns each "
        "matching conversation's summary and a matching message. Use when the user refers to "
        "something discussed before, or another thread is relevant."
    )
    parameters_schema = SearchConversationsParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import conversation_memory

        hits = conversation_memory.search_conversations(
            db, user.id, user.timezone, kwargs["query"], limit=kwargs.get("limit", 5)
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=hits,
            summary=f"{len(hits)} conversations matched '{kwargs['query']}'",
        )


class GetConversationParams(BaseModel):
    conversation_id: int = Field(..., description="ID of a past conversation")
    limit: int = Field(20, ge=1, le=60, description="Most recent messages to return")


class GetConversationTool(Tool):
    name = "get_conversation"
    description = "Read the recent messages of a past conversation, for exact details."
    parameters_schema = GetConversationParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import conversation_memory

        data = conversation_memory.conversation_transcript(
            db, user.id, kwargs["conversation_id"], kwargs.get("limit", 20)
        )
        if data is None:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Conversation #{kwargs['conversation_id']} not found.",
            )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=data,
            summary=f"Read {len(data['messages'])} messages from \"{data['title']}\"",
        )
