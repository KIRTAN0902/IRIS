"""Lead model -- lightweight CRM."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import LeadStatus


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(
        ForeignKey("startups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255), default=None)
    role: Mapped[str | None] = mapped_column(String(120), default=None)
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    phone: Mapped[str | None] = mapped_column(String(40), default=None)
    website: Mapped[str | None] = mapped_column(String(255), default=None)
    source: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(20), default=LeadStatus.LEAD.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    last_contacted: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    next_follow_up: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    startup = relationship("Startup", back_populates="leads")
    outreach_activities = relationship(
        "OutreachActivity", back_populates="lead", cascade="all, delete-orphan"
    )
