"""Notification Agent Tools for Notification Coworker."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.user import User
from app.services.notification_coworker_service import (
    IngestNotificationPayload,
    notification_coworker_service,
)


class GetNotificationStatusTool(Tool):
    name = "get_notification_status"
    description = (
        "Check the operational status of the Android notification-listener integration, "
        "including active connection status, ingested event count, and supported payment apps."
    )
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        status = notification_coworker_service.get_status(db, user.id)
        msg = status["message"]
        summary = f"Notification Coworker Status: {status['status'].upper()}.\n{msg}"
        return ToolResult(tool_name=self.name, success=True, data=status, summary=summary)


class GetNotificationEventsParams(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="Max recent notification events to inspect")


class GetNotificationEventsTool(Tool):
    name = "get_notification_events"
    description = "Inspect recent notification events ingested from authorized Android devices."
    parameters_schema = GetNotificationEventsParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        limit = kwargs.get("limit", 10)
        events = notification_coworker_service.get_recent_events(limit=limit)
        if not events:
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"events": [], "count": 0},
                summary="No recent notification events have been ingested yet.",
            )
        lines = [
            f"- [{e['status'].upper()}] {e['currency']} {e['amount']} to **{e['merchant']}** (Ref: {e.get('transaction_ref') or 'N/A'}) - Core: {e.get('core_response') or 'Pending'}"
            for e in events
        ]
        summary = f"Recent {len(events)} notification event(s):\n" + "\n".join(lines)
        return ToolResult(tool_name=self.name, success=True, data={"events": events, "count": len(events)}, summary=summary)


class IngestNotificationEventParams(BaseModel):
    package_name: str = Field(..., description="App package (e.g. com.google.android.apps.nbu.paisa.user)")
    title: str = Field("", description="Notification title")
    text: str = Field(..., description="Notification body text containing transaction alert")
    amount: float | None = Field(None, description="Pre-parsed amount if available")
    merchant: str | None = Field(None, description="Payee / merchant name if available")
    transaction_ref: str | None = Field(None, description="UPI reference or RRN")
    status: str = Field("completed", description="completed, pending, failed, reversed")


class IngestNotificationEventTool(Tool):
    name = "ingest_notification_event"
    description = (
        "Process and ingest a simulated or test payment notification event, validating "
        "information and forwarding to IRIS Core."
    )
    parameters_schema = IngestNotificationEventParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        payload = IngestNotificationPayload(
            package_name=kwargs["package_name"],
            title=kwargs.get("title", ""),
            text=kwargs["text"],
            amount=kwargs.get("amount"),
            merchant=kwargs.get("merchant"),
            transaction_ref=kwargs.get("transaction_ref"),
            status=kwargs.get("status", "completed"),
        )
        res = notification_coworker_service.ingest_event(db, user, payload)
        summary = res.get("message") or res.get("core_response") or "Notification processed."
        return ToolResult(tool_name=self.name, success=res.get("accepted", False), data=res, summary=summary)


def notification_tools() -> list[Tool]:
    return [
        GetNotificationStatusTool(),
        GetNotificationEventsTool(),
        IngestNotificationEventTool(),
    ]
