"""OutreachActivity model -- every outreach touchpoint with a lead."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import OutreachType


class OutreachActivity(Base):
    __tablename__ = "outreach_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    startup_id: Mapped[int] = mapped_column(
        ForeignKey("startups.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(15), default=OutreachType.EMAIL.value, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), index=True
    )
    message: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[str | None] = mapped_column(String(20), default=None, index=True)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    lead = relationship("Lead", back_populates="outreach_activities")
    startup = relationship("Startup", back_populates="outreach_activities")
