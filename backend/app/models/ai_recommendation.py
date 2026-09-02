"""AIRecommendation model -- audit trail and feedback loop for recommendations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None
    )
    recommendation_type: Mapped[str] = mapped_column(String(30), default="TASK")
    decision_type: Mapped[str] = mapped_column(String(30), default="SHOULD_DO", index=True)
    title: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    expected_outcome: Mapped[str | None] = mapped_column(Text, default=None)
    duration_minutes: Mapped[int | None] = mapped_column(default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    source: Mapped[str] = mapped_column(String(20), default="DETERMINISTIC")  # AI|DETERMINISTIC
    opportunity_cost: Mapped[str | None] = mapped_column(Text, default=None)
    evidence: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    # Feedback loop fields
    feedback: Mapped[str | None] = mapped_column(
        String(30), default=None, index=True
    )  # ACCEPTED | REJECTED | DEFERRED | COMPLETED | PARTIALLY_COMPLETED
    feedback_notes: Mapped[str | None] = mapped_column(Text, default=None)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), index=True
    )
