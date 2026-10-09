"""Daily routines (gym, yoga, reading...) the user ticks off, with a per-day log for streaks."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ALL_DAYS = "Mon,Tue,Wed,Thu,Fri,Sat,Sun"


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    # Same format as recurring schedules: "Mon,Wed,Fri".
    days_of_week: Mapped[str] = mapped_column(String(64), default=ALL_DAYS)
    # Optional usual time, "HH:MM" local.
    time: Mapped[str | None] = mapped_column(String(5), default=None)
    # How long it usually takes; with ``time`` this tells when it is "now".
    duration_min: Mapped[int | None] = mapped_column(Integer, default=None)
    # What to do, e.g. "Surya namaskar x12, pranayama 10 min".
    description: Mapped[str | None] = mapped_column(Text, default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    @property
    def days(self) -> list[str]:
        return [d.strip() for d in (self.days_of_week or ALL_DAYS).split(",") if d.strip()]

    def scheduled_on(self, day: date) -> bool:
        return day.strftime("%a") in self.days


class HabitLog(Base):
    """One row per day a habit was done (local calendar date)."""

    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "day", name="uq_habit_log_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), server_default=func.now())
