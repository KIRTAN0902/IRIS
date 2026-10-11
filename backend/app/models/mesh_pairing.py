"""Mesh Pairing & Cloud Relay models for Sovereign Cross-Device Continuity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MeshPairing(Base):
    """Stores permanently paired sovereign mesh devices (Mobile, Laptop, iPad)."""

    __tablename__ = "mesh_pairings"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_user_device_pairing"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Unique client-assigned identifier (e.g. "phone_iphone15_7b89f2")
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    device_name: Mapped[str] = mapped_column(String(120))
    device_type: Mapped[str] = mapped_column(String(32), default="phone_mobile")

    # Temporary 6-digit PIN code used during one-time pairing
    pairing_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    pairing_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Permanent cryptographic pairing token stored on the device
    pairing_token: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Cached device telemetry
    battery_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_charging: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    paired_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), index=True
    )

    user = relationship("User", back_populates="mesh_pairings")


class MeshRelayMessage(Base):
    """Durable cloud relay message log enabling cross-network device communication.
    
    Allows devices behind strict NAT / cellular 5G to communicate asynchronously
    without public IP ports or dynamic tunnels.
    """

    __tablename__ = "mesh_relay_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    sender_device_id: Mapped[str] = mapped_column(String(64), index=True)
    target_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    msg_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # List of device_ids that have consumed / processed this message
    consumed_by: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), index=True
    )

    user = relationship("User", back_populates="mesh_relay_messages")
