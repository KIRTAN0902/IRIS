"""RecurringSchedule model -- weekly recurring commitments and routine blocks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ScheduleBlockType


class RecurringSchedule(Base):
    __tablename__ = "recurring_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(30), default=ScheduleBlockType.FIXED.value, index=True)
    days_of_week: Mapped[str] = mapped_column(String(64), default="Mon,Tue,Wed,Thu,Fri,Sat,Sun")
    start_time: Mapped[str] = mapped_column(String(10))  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(10))  # "HH:MM"
    is_hard_constraint: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="recurring_schedules")

    @property
    def days_list(self) -> list[str]:
        return [d.strip() for d in self.days_of_week.split(",") if d.strip()]
