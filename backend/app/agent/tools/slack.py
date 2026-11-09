"""Slack Agent Tools for Workspace Coworker."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.user import User
from app.services.slack_service import slack_service


class SearchSlackMessagesParams(BaseModel):
    query: str = Field(..., min_length=1, description="Keywords or query to search across Slack discussions")
    limit: int = Field(default=8, ge=1, le=30, description="Max messages to return")


class SearchSlackMessagesTool(Tool):
    name = "search_slack_messages"
    description = (
        "Search messages and conversations across authorized Slack workspace channels by keyword or topic."
    )
    parameters_schema = SearchSlackMessagesParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        query = kwargs["query"]
        limit = kwargs.get("limit", 8)
        if not slack_service.is_configured(db, user.id):
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Slack is not connected.",
                summary="Slack workspace is not connected. Configure your Slack integration in Settings.",
            )
        try:
            results = await slack_service.search_messages(query=query, db=db, user_id=user.id, limit=limit)
            if not results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={"messages": [], "count": 0},
                    summary=f"No Slack messages found matching '{query}'.",
                )
            lines = [f"- **#{m['channel']}** ({m.get('username', 'user')}): {m.get('text', '')[:120]}" for m in results]
            summary = f"Found {len(results)} Slack message(s) matching '{query}':\n" + "\n".join(lines)
            return ToolResult(tool_name=self.name, success=True, data={"messages": results, "count": len(results)}, summary=summary)
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), summary=f"Slack search error: {exc}")


class GetSlackChannelHistoryParams(BaseModel):
    channel_id: str = Field(..., description="Channel ID or name in the Slack workspace")
    limit: int = Field(default=15, ge=1, le=50, description="Max messages to fetch")


class GetSlackChannelHistoryTool(Tool):
    name = "get_slack_channel_history"
    description = "Retrieve recent message history and discussion from a specific Slack channel."
    parameters_schema = GetSlackChannelHistoryParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        channel_id = kwargs["channel_id"]
        limit = kwargs.get("limit", 15)
        if not slack_service.is_configured(db, user.id):
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Slack is not connected.",
                summary="Slack workspace is not connected.",
            )
        try:
            messages = await slack_service.get_channel_history(channel_id=channel_id, db=db, user_id=user.id, limit=limit)
            summary = f"Retrieved {len(messages)} message(s) from Slack channel {channel_id}."
            return ToolResult(tool_name=self.name, success=True, data={"messages": messages, "count": len(messages)}, summary=summary)
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), summary=f"Slack history error: {exc}")


class ListSlackChannelsParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=50, description="Max channels to list")


class ListSlackChannelsTool(Tool):
    name = "list_slack_channels"
    description = "List accessible public and private channels in the authorized Slack workspace."
    parameters_schema = ListSlackChannelsParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        limit = kwargs.get("limit", 20)
        if not slack_service.is_configured(db, user.id):
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Slack is not connected.",
                summary="Slack workspace is not connected.",
            )
        try:
            channels = await slack_service.list_channels(db=db, user_id=user.id, limit=limit)
            lines = [f"- #{c['name']} (`{c['id']}`): {c.get('topic') or c.get('purpose') or 'no description'}" for c in channels]
            summary = f"Found {len(channels)} Slack channel(s):\n" + "\n".join(lines)
            return ToolResult(tool_name=self.name, success=True, data={"channels": channels, "count": len(channels)}, summary=summary)
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), summary=f"Slack channels error: {exc}")


class DraftSlackMessageParams(BaseModel):
    channel: str = Field(..., description="Target Slack channel name or ID")
    text: str = Field(..., min_length=1, description="Message text to draft")


class DraftSlackMessageTool(Tool):
    name = "draft_slack_message"
    description = "Prepare a draft response or message for an authorized Slack channel for user confirmation."
    parameters_schema = DraftSlackMessageParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        channel = kwargs["channel"]
        text = kwargs["text"]
        draft = slack_service.draft_message(channel=channel, text=text)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=draft,
            summary=draft["message"],
        )


class SendSlackMessageParams(BaseModel):
    channel: str = Field(..., description="Target Slack channel name or ID")
    text: str = Field(..., min_length=1, description="Message text to post")


class SendSlackMessageTool(Tool):
    name = "send_slack_message"
    description = "Send a message to an authorized Slack channel when explicitly instructed by the user."
    parameters_schema = SendSlackMessageParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        channel = kwargs["channel"]
        text = kwargs["text"]
        res = await slack_service.post_message(channel=channel, text=text, db=db, user_id=user.id)
        if not res.get("success"):
            return ToolResult(tool_name=self.name, success=False, error=res.get("error"), summary=f"Failed to post to Slack: {res.get('error')}")
        return ToolResult(tool_name=self.name, success=True, data=res, summary=res["message"])


def slack_tools() -> list[Tool]:
    return [
        SearchSlackMessagesTool(),
        GetSlackChannelHistoryTool(),
        ListSlackChannelsTool(),
        DraftSlackMessageTool(),
        SendSlackMessageTool(),
    ]
