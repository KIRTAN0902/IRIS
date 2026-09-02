"""Intelligence & Decision tools for the IRIS Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.intelligence.attention_engine import generate_attention_items
from app.intelligence.context import build_decision_context
from app.intelligence.decision_engine import decide_now, deterministic_decision
from app.intelligence.signals import SignalQuery, signal_repo
from app.models.ai_recommendation import AIRecommendation
from app.models.enums import DecisionFeedbackStatus
from app.models.user import User
from app.utils.datetime import utcnow

# --- 1. GetTodayStateTool ---


class GetTodayStateTool(Tool):
    name = "get_today_state"
    description = (
        "Retrieve today's schedule, flexible windows, urgent obligations, and bottleneck."
    )
    parameters_schema = None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        context = build_decision_context(db, user)
        cur_win = context.get("current_window", {})
        data = {
            "current_local_time": context.get("current_local_time"),
            "current_window": cur_win,
            "available_minutes": context.get("available_minutes", 0),
            "flexible_windows": context.get("flexible_windows", []),
            "fixed_commitments": context.get("fixed_constraints", {}).get("fixed_commitments", []),
            "urgent_obligations": context.get("urgent_obligations", []),
            "startup_state": context.get("startup_state"),
        }
        mins = context.get("available_minutes", 0)
        win_name = cur_win.get("active_block_name", "Open")
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=data,
            summary=f"Today: {mins}m flexible time available. Current window: {win_name}.",
        )


# --- 2. GetAttentionItemsTool ---


class GetAttentionItemsTool(Tool):
    name = "get_attention_items"
    description = (
        "Retrieve prioritized attention items ranked by deterministic urgency/impact score."
    )
    parameters_schema = None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        signals = signal_repo.gather_all_signals(
            db, user, SignalQuery(user_id=user.id, now_utc=utcnow())
        )
        items = generate_attention_items(db, user, signals=signals)
        data = [
            {
                "id": it.id,
                "type": it.type,
                "domain": it.domain,
                "title": it.title,
                "description": it.description,
                "score": it.score,
                "urgency": it.urgency,
                "impact": it.impact,
                "suggested_action": it.suggested_action,
            }
            for it in items
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"attention_items": data},
            summary=f"Found {len(data)} attention items requiring focus.",
        )


# --- 3. GetDecisionRecommendationTool ---


class GetDecisionRecommendationParams(BaseModel):
    available_minutes: int | None = Field(
        None, ge=5, le=1440, description="Available minutes to allocate"
    )
    use_ai: bool = Field(True, description="Whether to use AI reasoning or deterministic rules")


class GetDecisionRecommendationTool(Tool):
    name = "get_decision_recommendation"
    description = (
        "Generate a contextual recommendation answering 'What should I do right now?'"
    )
    parameters_schema = GetDecisionRecommendationParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        avail = kwargs.get("available_minutes")
        use_ai = kwargs.get("use_ai", True)
        if use_ai:
            rec, _ = await decide_now(db, user, available_minutes=avail)
        else:
            rec = deterministic_decision(db, user, available_minutes=avail)

        data = {
            "title": rec.title,
            "decision_type": rec.decision_type,
            "reason": rec.reason,
            "duration_minutes": rec.duration_minutes,
            "expected_outcome": rec.expected_outcome,
            "confidence": rec.confidence,
            "opportunity_cost": rec.opportunity_cost,
            "evidence": rec.evidence,
            "task_id": rec.task_id,
        }
        summary_text = (
            f"Recommendation ({rec.decision_type}): '{rec.title}' ({rec.duration_minutes or 0}m)."
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=data,
            summary=summary_text,
        )


# --- 4. RecordDecisionFeedbackTool ---


class RecordDecisionFeedbackParams(BaseModel):
    recommendation_id: int = Field(..., description="ID of the recommendation")
    feedback: DecisionFeedbackStatus = Field(
        ..., description="ACCEPTED, REJECTED, DEFERRED, or COMPLETED"
    )
    notes: str | None = Field(None, description="Optional user notes")


class RecordDecisionFeedbackTool(Tool):
    name = "record_decision_feedback"
    description = "Record explicit user feedback (ACCEPTED, REJECTED, etc.) on a recommendation."
    parameters_schema = RecordDecisionFeedbackParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        rec_id = kwargs["recommendation_id"]
        fb = kwargs["feedback"]
        notes = kwargs.get("notes")

        rec = (
            db.query(AIRecommendation)
            .filter(AIRecommendation.id == rec_id, AIRecommendation.user_id == user.id)
            .first()
        )
        if not rec:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Recommendation #{rec_id} not found.",
            )

        rec.feedback = fb
        rec.feedback_notes = notes
        rec.feedback_at = utcnow()
        db.commit()
        db.refresh(rec)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"recommendation_id": rec.id, "feedback": rec.feedback},
            summary=f"Recorded feedback '{rec.feedback}' for recommendation #{rec.id}.",
            audit_event={
                "action": "RECORD_FEEDBACK",
                "recommendation_id": rec.id,
                "feedback": rec.feedback,
            },
        )


# --- 5. GetDecisionHistoryTool ---


class GetDecisionHistoryParams(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="Max number of past decisions to return")


class GetDecisionHistoryTool(Tool):
    name = "get_decision_history"
    description = "Retrieve the history of past AI and deterministic recommendations and feedback."
    parameters_schema = GetDecisionHistoryParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        limit = kwargs.get("limit", 10)
        recs = (
            db.query(AIRecommendation)
            .filter(AIRecommendation.user_id == user.id)
            .order_by(AIRecommendation.created_at.desc())
            .limit(limit)
            .all()
        )
        data = [
            {
                "id": r.id,
                "recommendation_type": r.recommendation_type,
                "title": r.title,
                "reason": r.reason,
                "source": r.source,
                "feedback": r.feedback,
                "feedback_notes": r.feedback_notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recs
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"decisions": data, "total": len(data)},
            summary=f"Retrieved {len(data)} past decision recommendations.",
        )


# --- 6. GetCurrentStateTool (Alias for get_today_state / snapshot) ---


class GetCurrentStateTool(Tool):
    name = "get_current_state"
    description = (
        "Retrieve comprehensive current state snapshot including time, flexible windows, and tasks."
    )
    parameters_schema = None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        tool = GetTodayStateTool()
        res = await tool.run(db, user, **kwargs)
        res.tool_name = self.name
        return res


# --- 7. GetCurrentRecommendationTool (Alias for get_decision_recommendation) ---


class GetCurrentRecommendationTool(Tool):
    name = "get_current_recommendation"
    description = "Retrieve or compute the current recommendation for what to do right now."
    parameters_schema = GetDecisionRecommendationParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        tool = GetDecisionRecommendationTool()
        res = await tool.run(db, user, **kwargs)
        res.tool_name = self.name
        return res

