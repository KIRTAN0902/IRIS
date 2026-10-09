"""Gym workout plans by weekday, their exercises, and per-day exercise tick-offs.

Sets/reps, time and weight are free text because people write them many ways
("4x5-8", "2-3x20", "7.5x2", "45s").
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    # e.g. "Chest, Shoulders, Triceps"
    focus: Mapped[str | None] = mapped_column(String(160), default=None)
    # Same format as routines: "Sun" or "Mon,Thu". Empty = not tied to a day.
    days_of_week: Mapped[str] = mapped_column(String(64), default="")
    # e.g. "75-85 min"
    duration: Mapped[str | None] = mapped_column(String(40), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    exercises = relationship(
        "WorkoutExercise",
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="WorkoutExercise.position",
    )

    @property
    def days(self) -> list[str]:
        return [d.strip() for d in (self.days_of_week or "").split(",") if d.strip()]


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey("workouts.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(120))
    sets_reps: Mapped[str | None] = mapped_column(String(40), default=None)
    time: Mapped[str | None] = mapped_column(String(40), default=None)
    muscles: Mapped[str | None] = mapped_column(String(160), default=None)
    weight: Mapped[str | None] = mapped_column(String(40), default=None)
    notes: Mapped[str | None] = mapped_column(String(255), default=None)

    workout = relationship("Workout", back_populates="exercises")


class WorkoutLog(Base):
    """An exercise ticked off on a given (local) day."""

    __tablename__ = "workout_logs"
    __table_args__ = (UniqueConstraint("exercise_id", "day", name="uq_workout_log_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey("workouts.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("workout_exercises.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), server_default=func.now())
