"""Goal model -- hierarchical (parent/child) with measurable progress."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import GoalStatus, LifeArea


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    parent_goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), default=None, index=True
    )
    area: Mapped[str] = mapped_column(String(20), default=LifeArea.PERSONAL.value, index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    target_value: Mapped[float | None] = mapped_column(Float, default=None)
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str | None] = mapped_column(String(50), default=None)
    status: Mapped[str] = mapped_column(String(15), default=GoalStatus.ACTIVE.value, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="goals")
    parent = relationship("Goal", remote_side="Goal.id", back_populates="children")
    children = relationship("Goal", back_populates="parent", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="goal")

    @property
    def progress_fraction(self) -> float:
        if not self.target_value:
            return 0.0
        return max(0.0, min(1.0, self.current_value / self.target_value))
