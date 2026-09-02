"""CalendarEvent model -- internal + external (e.g., Google Calendar later)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EventSource


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "external_id", name="uq_calendar_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    location: Mapped[str | None] = mapped_column(String(255), default=None)
    source: Mapped[str] = mapped_column(String(20), default=EventSource.INTERNAL.value, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="calendar_events")

    @property
    def duration_minutes(self) -> int:
        return max(0, int((self.end_time - self.start_time).total_seconds() // 60))
