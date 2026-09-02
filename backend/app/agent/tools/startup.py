"""Startup & CRM tools for the IRIS Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.enums import OutreachResult, OutreachType
from app.models.user import User
from app.schemas.outreach import OutreachActivityCreate
from app.services import analytics_service, startup_service

# --- 1. GetStartupStatusTool ---


class GetStartupStatusTool(Tool):
    name = "get_startup_status"
    description = (
        "Retrieve startup pipeline, customer count, outreach totals, and active experiments."
    )
    parameters_schema = None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        try:
            metrics = analytics_service.startup_analytics(db, user.id)
        except Exception:
            metrics = None

        if not metrics:
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=None,
                summary="No startup profile configured.",
            )
        data = {
            "startup_name": metrics.startup_name,
            "leads_total": metrics.pipeline.leads_total,
            "outreach_total": metrics.outreach.total,
            "reply_rate": metrics.outreach.reply_rate,
            "meeting_rate": metrics.outreach.meeting_rate,
            "customers": metrics.customers,
            "goals_behind": metrics.goals_behind,
            "running_experiments": metrics.running_experiments,
        }
        summary_str = (
            f"Startup '{metrics.startup_name}': {metrics.customers} customers, "
            f"{metrics.outreach.total} outreach, reply rate {metrics.outreach.reply_rate}%."
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=data,
            summary=summary_str,
        )


# --- 2. LogOutreachTool ---


class LogOutreachParams(BaseModel):
    lead_id: int = Field(..., description="ID of the lead contacted")
    type: OutreachType = Field(
        OutreachType.EMAIL, description="Type (EMAIL, LINKEDIN, CALL, WHATSAPP)"
    )
    result: OutreachResult = Field(
        OutreachResult.SENT, description="Result (SENT, REPLIED, MEETING_BOOKED, etc.)"
    )
    message: str | None = Field(None, description="Message copy or subject line")
    notes: str | None = Field(None, description="Notes on the interaction")


class LogOutreachTool(Tool):
    name = "log_outreach"
    description = "Log an outreach activity (email, call, LinkedIn message) to a lead."
    parameters_schema = LogOutreachParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        lead_id = kwargs["lead_id"]
        lead = startup_service.get_lead(db, user.id, lead_id)
        outreach_in = OutreachActivityCreate(
            lead_id=lead_id,
            startup_id=lead.startup_id,
            type=kwargs.get("type", OutreachType.EMAIL),
            result=kwargs.get("result", OutreachResult.SENT),
            message=kwargs.get("message"),
            notes=kwargs.get("notes"),
        )
        activity = startup_service.log_outreach(db, user.id, outreach_in.model_dump())
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"activity_id": activity.id, "lead_id": lead_id, "result": activity.result},
            summary=f"Logged {activity.type} outreach to {lead.name} (result: {activity.result}).",
            audit_event={"action": "LOG_OUTREACH", "lead_id": lead_id, "type": activity.type},
        )


# --- 3. GetOutreachStatusTool ---


class GetOutreachStatusParams(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="Max number of recent outreach logs to return")


class GetOutreachStatusTool(Tool):
    name = "get_outreach_status"
    description = (
        "Retrieve recent outreach activities, conversion rates, and pipeline "
        "status for the startup."
    )
    parameters_schema = GetOutreachStatusParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        try:
            metrics = analytics_service.startup_analytics(db, user.id)
        except Exception:
            metrics = None
        limit = kwargs.get("limit", 10)
        from app.models.outreach import OutreachActivity
        from app.models.startup import Startup

        recent_acts = (
            db.query(OutreachActivity)
            .join(Startup, OutreachActivity.startup_id == Startup.id)
            .filter(Startup.user_id == user.id)
            .order_by(OutreachActivity.timestamp.desc())
            .limit(limit)
            .all()
        )
        recent_data = [
            {
                "id": a.id,
                "lead_id": a.lead_id,
                "type": a.type,
                "result": a.result,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "message": a.message,
            }
            for a in recent_acts
        ]
        outreach_metrics = metrics.outreach if metrics else None
        data = {
            "total_outreach": outreach_metrics.total if outreach_metrics else 0,
            "reply_rate": outreach_metrics.reply_rate if outreach_metrics else 0.0,
            "meeting_rate": outreach_metrics.meeting_rate if outreach_metrics else 0.0,
            "recent_activities": recent_data,
        }
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=data,
            summary=(
                f"Outreach: {data['total_outreach']} total, "
                f"{data['reply_rate']}% reply rate, {len(recent_data)} recent logs."
            ),
        )

