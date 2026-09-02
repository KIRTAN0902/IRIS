"""FocusSession model -- planned vs actual work duration signal."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import FocusStatus


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    planned_duration: Mapped[int | None] = mapped_column(Integer, default=None)  # minutes
    actual_duration: Mapped[int | None] = mapped_column(Integer, default=None)  # minutes
    status: Mapped[str] = mapped_column(String(15), default=FocusStatus.RUNNING.value, index=True)
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="focus_sessions")
    task = relationship("Task", back_populates="focus_sessions")
