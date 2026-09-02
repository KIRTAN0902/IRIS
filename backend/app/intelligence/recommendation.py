"""Decision intelligence recommendation models.

Structured schemas for IRIS decisions, recommendations, multi-step sequences,
trade-off alternatives, and missing information requests.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DecisionType(StrEnum):
    """Classification of the urgency and nature of the decision."""

    MUST_DO = "MUST_DO"  # Urgent obligation, hard deadline, critical fix
    SHOULD_DO = "SHOULD_DO"  # Best strategic use of flexible time / bottleneck focus
    COULD_DO = "COULD_DO"  # Valuable but optional / flexible opportunity
    WAIT = "WAIT"  # Deliberate rest, recharge, or waiting for external event
    ASK_USER = "ASK_USER"  # Critical context missing; clarification required


class AlternativeOption(BaseModel):
    """An alternative option considered and why it was deferred/ranked lower."""

    title: str
    area: str | None = None
    trade_off_reason: str


class DecisionStep(BaseModel):
    """A step in a multi-step recommended sequence."""

    step_number: int
    title: str
    task_id: int | None = None
    area: str | None = None
    duration_minutes: int
    reason: str
    expected_outcome: str | None = None


class DecisionRecommendationOut(BaseModel):
    """Structured decision output from the IRIS Decision Intelligence Layer."""

    recommendation_type: Literal[
        "TASK", "BREAK", "REST", "STRATEGIC_NOTE", "SEQUENCE", "ASK_USER"
    ] = "TASK"
    decision_type: DecisionType = DecisionType.SHOULD_DO
    decision: str | None = Field(
        None, description="Identifier of the decision, e.g. STARTUP_OUTREACH, COLLEGE_ASSIGNMENT"
    )
    task_id: int | None = None
    title: str = Field(..., min_length=1)
    reason: str = Field(..., description="Contextual reason explaining trade-offs and facts")
    duration_minutes: int | None = Field(None, ge=1, le=24 * 60)
    expected_outcome: str | None = Field(
        None, description="Concrete, measurable outcome (not just 'work on X')"
    )
    confidence: float = Field(0.75, ge=0.0, le=1.0)
    opportunity_cost: str | None = Field(
        None, description="Trade-off note on what is being deferred and why"
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Concrete data points or observations supporting this decision",
    )
    observed_facts: list[str] = Field(
        default_factory=list,
        description="Directly observed facts from the context",
    )
    derived_insights: list[str] = Field(
        default_factory=list,
        description="System-calculated derivations and progress metrics",
    )
    alternatives_considered: list[AlternativeOption] = Field(default_factory=list)
    sequence: list[DecisionStep] = Field(
        default_factory=list,
        description="Multi-step sequence when available time accommodates multiple tasks",
    )
    missing_information: str | None = Field(
        None, description="Specific missing information when decision_type is ASK_USER"
    )
