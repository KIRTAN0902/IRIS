"""Task model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import LifeArea, TaskPriority, TaskStatus


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    area: Mapped[str] = mapped_column(String(20), default=LifeArea.PERSONAL.value, index=True)
    priority: Mapped[str] = mapped_column(String(10), default=TaskPriority.MEDIUM.value, index=True)
    status: Mapped[str] = mapped_column(String(15), default=TaskStatus.TODO.value, index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    estimated_duration: Mapped[int | None] = mapped_column(Integer, default=None)  # minutes
    actual_duration: Mapped[int | None] = mapped_column(Integer, default=None)  # minutes
    energy_level: Mapped[str | None] = mapped_column(String(15), default=None)
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), default=None, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    user = relationship("User", back_populates="tasks")
    goal = relationship("Goal", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    time_blocks = relationship("TimeBlock", back_populates="task")
    focus_sessions = relationship("FocusSession", back_populates="task")

    @property
    def is_open(self) -> bool:
        return self.status in (TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value)

    @property
    def is_overdue(self) -> bool:
        from app.utils.datetime import utcnow

        return self.deadline is not None and self.is_open and self.deadline < utcnow()
