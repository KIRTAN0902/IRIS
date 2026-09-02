"""DailyReview model -- one per user per local calendar day."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DailyReview(Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_review_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    completed_tasks: Mapped[int | None] = mapped_column(Integer, default=None)
    incomplete_tasks: Mapped[int | None] = mapped_column(Integer, default=None)
    blockers: Mapped[str | None] = mapped_column(Text, default=None)
    productivity_rating: Mapped[int | None] = mapped_column(Integer, default=None)  # 1..5
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    ai_summary: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="daily_reviews")
