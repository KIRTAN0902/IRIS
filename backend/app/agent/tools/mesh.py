"""IRIS Mesh Agent Tools: Enables the AI Assistant to control connected devices.

Tools:
- ring_my_phone: Trigger sound alert on phone (Find My Phone)
- lock_workstation: Remotely lock Windows workstation
- sync_clipboard: Push text to Universal Clipboard across all devices
- get_device_mesh_status: View connected devices and battery levels
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.user import User
from app.services import mesh_service as ms


class SyncClipboardParams(BaseModel):
    text: str = Field(..., description="Text, link, or code snippet to push to Universal Clipboard")


class RingMyPhoneTool(Tool):
    name = "ring_my_phone"
    description = (
        "Find My Phone: Sends a high-priority remote sound alert to ring your phone at maximum volume "
        "across the IRIS Mesh."
    )
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        msg = ms.MeshMessage(
            type="REMOTE_COMMAND",
            sender_device="iris_agent",
            payload={"command": "RING_PHONE"},
        )
        await ms.hub.broadcast(msg, exclude_sender=False)
        phones = [d for d in ms.hub.devices.values() if "phone" in d.device_type]
        count = len(phones)
        summary = f"Triggered ring alert to {count} connected phone(s)." if count else "Triggered ring alert across all mesh listeners."
        return ToolResult(tool_name=self.name, success=True, data={"alert": "RING_PHONE", "devices_notified": count}, summary=summary)


class LockWorkstationTool(Tool):
    name = "lock_workstation"
    description = "Remotely lock the Windows laptop immediately for privacy."
    read_only = False
    is_destructive = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        success = ms.lock_windows_pc()
        summary = "Locked Windows laptop workstation." if success else "Failed to lock workstation."
        return ToolResult(tool_name=self.name, success=success, data={"locked": success}, summary=summary)


class SyncClipboardTool(Tool):
    name = "sync_clipboard"
    description = "Push text, links, or code snippets to the Universal Clipboard so it is ready to paste on your phone."
    parameters_schema = SyncClipboardParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        text = kwargs["text"]
        ms.hub.set_clipboard(text, sender_id="iris_agent")
        msg = ms.MeshMessage(
            type="CLIPBOARD_SYNC",
            sender_device="iris_agent",
            payload={"text": text},
        )
        await ms.hub.broadcast(msg, exclude_sender=False)
        summary = f"Copied {len(text)} characters to Universal Clipboard."
        return ToolResult(tool_name=self.name, success=True, data={"length": len(text), "preview": text[:60]}, summary=summary)


class GetDeviceMeshStatusTool(Tool):
    name = "get_device_mesh_status"
    description = "Check which devices (laptop, mobile phone) are connected to the IRIS Mesh and inspect battery levels."
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs

        active_devices = [d.model_dump(mode="json") for d in ms.hub.devices.values()]
        paired_devices = [
            {
                "id": p.id,
                "device_id": p.device_id,
                "device_name": p.device_name,
                "device_type": p.device_type,
                "battery_level": p.battery_level,
                "last_seen_at": p.last_seen_at.isoformat() if p.last_seen_at else None,
            }
            for p in mrs.list_paired_devices(db, user.id)
        ]
        battery = ms.get_windows_battery()
        summary = f"{len(active_devices)} device(s) connected to IRIS Mesh."
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "devices": active_devices,
                "active_devices": active_devices,
                "paired_devices": paired_devices,
                "host_battery": battery,
            },
            summary=summary,
        )


class LaunchAppParams(BaseModel):
    app: str = Field(
        default="antigravity",
        description="Application to launch on the laptop (e.g. 'antigravity', 'antigravity ide', 'vscode', 'terminal', 'chrome')",
    )
    argument: str | None = Field(
        None,
        description="Optional folder, workspace path, or URL to open in the app (e.g. 'C:\\kirtan\\IRIS')",
    )


class LaunchLaptopAppTool(Tool):
    name = "launch_laptop_app"
    description = (
        "Launch or open a desktop application on your Windows laptop remotely "
        "(e.g. 'open antigravity on laptop', 'launch VS Code', 'open terminal')."
    )
    parameters_schema = LaunchAppParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        app_name = kwargs.get("app", "antigravity")
        arg = kwargs.get("argument")
        res = ms.launch_windows_app(app_name=app_name, argument=arg)

        # Broadcast remote command
        msg = ms.MeshMessage(
            type="REMOTE_COMMAND",
            sender_device="iris_agent",
            payload={"command": "LAUNCH_APP", "app": app_name, "argument": arg},
        )
        await ms.hub.broadcast(msg, exclude_sender=False)
        return ToolResult(
            tool_name=self.name,
            success=res.get("success", False),
            data=res,
            summary=res.get("message", f"Launched {app_name} on laptop."),
        )


def mesh_tools() -> list[Tool]:
    """Factory returning all IRIS Mesh continuity tools."""
    return [
        RingMyPhoneTool(),
        LockWorkstationTool(),
        SyncClipboardTool(),
        GetDeviceMeshStatusTool(),
        LaunchLaptopAppTool(),
    ]
