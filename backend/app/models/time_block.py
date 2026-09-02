"""TimeBlock model -- planned segments of time; overlap detection supported."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import TimeBlockStatus, TimeBlockType


class TimeBlock(Base):
    __tablename__ = "time_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None, index=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    type: Mapped[str] = mapped_column(String(15), default=TimeBlockType.FOCUS.value, index=True)
    status: Mapped[str] = mapped_column(
        String(15), default=TimeBlockStatus.SCHEDULED.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="time_blocks")
    task = relationship("Task", back_populates="time_blocks")

    @property
    def duration_minutes(self) -> int:
        return max(0, int((self.end_time - self.start_time).total_seconds() // 60))

    @staticmethod
    def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
        """Half-open interval overlap: [start, end)."""
        return a_start < b_end and b_start < a_end
