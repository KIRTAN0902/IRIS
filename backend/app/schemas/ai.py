"""AI request/response schemas.

Every Gemini response is validated against these models. If validation fails,
the AI layer retries once and then falls back to deterministic output or a
controlled error -- raw model output never reaches API consumers.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RecommendationOut(BaseModel):
    """Structured 'what should I do now' recommendation."""

    recommendation_type: Literal[
        "TASK", "BREAK", "REST", "STRATEGIC_NOTE", "SEQUENCE", "ASK_USER"
    ] = "TASK"
    decision_type: Literal["MUST_DO", "SHOULD_DO", "COULD_DO", "WAIT", "ASK_USER"] = "SHOULD_DO"
    decision: str | None = None
    task_id: int | None = None
    title: str = Field(..., min_length=1)
    reason: str
    duration_minutes: int | None = Field(None, ge=1, le=24 * 60)
    expected_outcome: str | None = None
    confidence: float = Field(0.5, ge=0, le=1)
    opportunity_cost: str | None = None
    alternatives_considered: list[Any] | None = None
    sequence: list[Any] | None = None
    missing_information: str | None = None


class PlanDayBlock(BaseModel):
    task_id: int | None = None
    start: datetime
    end: datetime
    reason: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": 12,
                "start": "2026-08-24T09:00:00",
                "end": "2026-08-24T10:30:00",
                "reason": "Deadline tomorrow; deep-work slot.",
            }
        }
    }


class PlanDayOut(BaseModel):
    """A draft day plan. NOT persisted until the client confirms it."""

    date: date
    blocks: list[PlanDayBlock]
    unscheduled_task_ids: list[int] = []
    summary: str | None = None


class DailyReviewOut(BaseModel):
    summary: str
    college_status: str | None = None
    internship_status: str | None = None
    startup_status: str | None = None
    main_problem: str | None = None
    recommendation_for_tomorrow: str | None = None


class StartupAnalysisOut(BaseModel):
    observation: str
    possible_cause: str | None = None
    recommendation: str | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    data_evidence: dict[str, float | int] | None = Field(
        None, description="Observed metrics backing the observation (facts, not speculation)"
    )


class AskIRISOut(BaseModel):
    answer: str
    follow_ups: list[str] = []
    ai_available: bool = True


# --- Response envelopes -------------------------------------------------------
# Extend the AI-validated models with provenance metadata. The inner schemas are
# what Gemini output is validated against; these add where the answer came from.


class AIMeta(BaseModel):
    source: Literal["AI", "DETERMINISTIC"] = "DETERMINISTIC"
    ai_available: bool = False


class RecommendationResponse(AIMeta, RecommendationOut):
    pass


class PlanDayResponse(AIMeta, PlanDayOut):
    pass


class DailyReviewResponse(AIMeta, DailyReviewOut):
    pass


class StartupAnalysisResponse(AIMeta, StartupAnalysisOut):
    pass
