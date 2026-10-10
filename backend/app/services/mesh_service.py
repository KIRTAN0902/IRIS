"""IRIS Mesh Service: Core device continuity, Universal Clipboard, and remote control.

Manages real-time bidirectional events between Laptop (Windows) and Mobile devices:
1. Universal Clipboard & File Drop (AirDrop equivalent)
2. Remote Command & Hardware Control (Lock PC, ring phone, battery reporting)
3. State Handoff (transfer focus sessions and workflows)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any
import uuid

from fastapi import WebSocket
from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger(__name__)

# File Drop Storage Directory
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "mesh_vault"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class DeviceInfo(BaseModel):
    device_id: str
    device_type: str  # "laptop_windows" | "phone_mobile"
    name: str
    connected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_ping: datetime = Field(default_factory=lambda: datetime.now(UTC))
    battery_level: int | None = None  # 0-100
    is_charging: bool | None = None


class MeshMessage(BaseModel):
    msg_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str  # "CLIPBOARD_SYNC" | "FILE_DROP" | "REMOTE_COMMAND" | "HANDOFF" | "DEVICE_STATE" | "PING"
    sender_device: str
    target_device: str | None = None  # None = broadcast to all other devices
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class MeshHub:
    """Manages active device connections and broadcasts continuity events."""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.devices: dict[str, DeviceInfo] = {}
        self.latest_clipboard: str = ""
        self.latest_clipboard_updated_at: datetime | None = None
        self.latest_handoff_state: dict[str, Any] = {}

    async def connect(self, device_id: str, device_type: str, name: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[device_id] = websocket
        self.devices[device_id] = DeviceInfo(
            device_id=device_id,
            device_type=device_type,
            name=name,
        )
        logger.info("Mesh device connected: %s (%s)", name, device_id)
        # Notify all devices of updated device registry
        await self.broadcast_device_states()

    def disconnect(self, device_id: str) -> None:
        self.active_connections.pop(device_id, None)
        self.devices.pop(device_id, None)
        logger.info("Mesh device disconnected: %s", device_id)

    async def broadcast(self, message: MeshMessage, exclude_sender: bool = True) -> None:
        raw = message.model_dump_json()
        dead_connections: list[str] = []

        for dev_id, ws in list(self.active_connections.items()):
            if exclude_sender and dev_id == message.sender_device:
                continue
            if message.target_device and message.target_device != dev_id:
                continue

            try:
                await ws.send_text(raw)
            except Exception:
                dead_connections.append(dev_id)

        for dev_id in dead_connections:
            self.disconnect(dev_id)

    async def broadcast_device_states(self) -> None:
        """Broadcasts current connected devices list to everyone."""
        msg = MeshMessage(
            type="DEVICE_STATE",
            sender_device="system",
            payload={
                "devices": [d.model_dump(mode="json") for d in self.devices.values()]
            },
        )
        await self.broadcast(msg, exclude_sender=False)

    def set_clipboard(self, text: str, sender_id: str = "laptop_windows") -> None:
        """Updates internal clipboard cache."""
        self.latest_clipboard = text
        self.latest_clipboard_updated_at = datetime.now(UTC)

    def get_clipboard(self) -> dict[str, Any]:
        return {
            "text": self.latest_clipboard,
            "updated_at": self.latest_clipboard_updated_at.isoformat() if self.latest_clipboard_updated_at else None,
        }

    def set_handoff(self, state_type: str, data: dict[str, Any], sender_id: str) -> None:
        self.latest_handoff_state = {
            "type": state_type,
            "data": data,
            "sender": sender_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }


# Global Mesh Hub Singleton
hub = MeshHub()


# --- Windows Desktop System Actions ---


def lock_windows_pc() -> bool:
    """Locks the Windows workstation remotely."""
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return True
    except Exception as exc:
        logger.error("Failed to lock Windows workstation: %s", exc)
        return False


def get_windows_battery() -> dict[str, Any] | None:
    """Reads laptop battery and AC status on Windows."""
    try:
        import ctypes
        from ctypes import wintypes

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", wintypes.BYTE),
                ("BatteryFlag", wintypes.BYTE),
                ("BatteryLifePercent", wintypes.BYTE),
                ("SystemStatusFlag", wintypes.BYTE),
                ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD),
            ]

        status = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            is_charging = status.ACLineStatus == 1
            percent = status.BatteryLifePercent
            return {
                "percent": percent if percent <= 100 else None,
                "is_charging": is_charging,
                "ac_status": "Plugged In" if is_charging else "On Battery",
            }
    except Exception as exc:
        logger.debug("Could not read power status: %s", exc)
    return None
