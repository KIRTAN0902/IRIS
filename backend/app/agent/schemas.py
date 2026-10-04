"""Pydantic schemas for Agent interaction, tool parameters, and chat endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    """A structured tool call requested by the agent."""

    tool_name: str = Field(..., description="Name of the tool to execute")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Dictionary of keyword arguments"
    )


class ToolResult(BaseModel):
    """The result of executing a tool."""

    tool_name: str
    success: bool
    data: dict[str, Any] | list[Any] | str | int | float | None = None
    error: str | None = None
    summary: str | None = Field(
        None, description="Human-friendly summary of the outcome for user display"
    )
    audit_event: dict[str, Any] | None = None


class AgentResponseSchema(BaseModel):
    """Structured LLM output for an agent turn."""

    thought: str = Field(
        "", description="Brief internal reasoning about user intent and needed actions"
    )
    actions: list[ToolCall] = Field(
        default_factory=list,
        description="List of tools to execute in sequence (if action requested)",
    )
    continue_after_actions: bool = Field(
        False,
        description=(
            "Set true when you need to see the results of 'actions' before giving your "
            "final answer (e.g. after calling a get_/search_ tool). You will be called "
            "again with the results. Leave false when 'message' is already your final reply."
        ),
    )
    message: str = Field(
        ..., description="Conversational reply to user, grounded in IRIS context and tool results"
    )
    actions_summary: list[str] = Field(
        default_factory=list,
        description="Friendly list of executed actions (e.g. 'Added task X')",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Key data points or trade-off facts supporting this response",
    )
    recommended_action: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured recommendation payload (e.g. task_id, duration_minutes)",
    )
    missing_information: str | None = Field(
        default=None,
        description="Honest statement of missing context (e.g. 'Gmail is not connected')",
    )


class ChatMessageIn(BaseModel):
    """User input payload for a chat message."""

    content: str = Field(..., min_length=1, max_length=4000, description="User's input")
    voice: bool = Field(False, description="Spoken by voice; the reply will be read aloud")
    defer_memory: bool = Field(
        False, description="Reply first; the client then calls POST /chat/messages/{id}/remember"
    )


class ChatMessageOut(BaseModel):
    """Single chat message returned by the API."""

    id: int
    conversation_id: int
    role: str
    content: str
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_action: dict[str, Any] | None = None
    source: str = "AI"
    memories_updated: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime



class ConversationOut(BaseModel):
    """Summary of a conversation thread."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None = None
    topics: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(BaseModel):
    """Conversation thread with full message history."""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageOut]
