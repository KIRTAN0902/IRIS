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
        host_info = mrs.get_laptop_host_info(db, user.id)
        is_host_online = host_info.get("is_online", False) or mrs.is_local_windows_host()

        # Ensure the Windows host laptop is explicitly listed as active and online
        if is_host_online:
            active_devices.append({
                "device_id": mrs.LAPTOP_HOST_DEVICE_ID,
                "device_name": host_info.get("device_name", "Windows Workstation"),
                "device_type": "laptop_windows",
                "battery_level": host_info.get("battery_level"),
                "is_charging": host_info.get("is_charging"),
                "is_online": True,
                "status": "online",
                "capabilities": ["terminal_command", "antigravity", "file_surfing", "desktop_control"],
            })

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
        battery = ms.get_windows_battery() or {"percent": host_info.get("battery_level"), "is_charging": host_info.get("is_charging")}

        summary_parts = []
        if is_host_online:
            bat_pct = host_info.get("battery_level") or (battery.get("percent") if isinstance(battery, dict) else None)
            bat_txt = f" (Battery: {bat_pct}%)" if bat_pct is not None else ""
            summary_parts.append(f"Windows Laptop workstation is ONLINE and ACTIVE{bat_txt} with full terminal & filesystem access.")
        else:
            summary_parts.append("Windows Laptop is currently offline.")

        other_count = len(ms.hub.devices.values())
        if other_count:
            summary_parts.append(f"{other_count} companion device(s) connected.")

        summary = " ".join(summary_parts)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "laptop_online": is_host_online,
                "terminal_access_available": is_host_online,
                "devices": active_devices,
                "active_devices": active_devices,
                "paired_devices": paired_devices,
                "host_battery": battery,
                "laptop_host": host_info,
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


class RunTerminalCommandParams(BaseModel):
    command: str = Field(
        ...,
        description="PowerShell or shell CLI command to execute on the laptop (e.g. 'git status', 'dir', 'npm test', 'tasklist', 'python script.py')",
    )
    working_dir: str | None = Field(
        default=r"C:\kirtan\IRIS",
        description="Working directory on the laptop to run the command in (defaults to 'C:\\kirtan\\IRIS')",
    )


class RunLaptopTerminalCommandTool(Tool):
    name = "run_laptop_terminal_command"
    description = (
        "Execute a terminal command or script on your Windows laptop remotely and receive the output. "
        "Use when the user asks via voice or chat to run a terminal/CLI command, check git status, "
        "run tests, build a project, list directory files, or inspect system processes on their laptop."
    )
    parameters_schema = RunTerminalCommandParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs
        import secrets

        cmd = kwargs["command"]
        cwd = kwargs.get("working_dir")

        if mrs.is_local_windows_host():
            res = ms.execute_terminal_command(command=cmd, cwd=cwd)
        else:
            req_id = secrets.token_hex(6)
            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_voice_agent",
                target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                msg_type="TERMINAL_EXEC",
                payload={"req_id": req_id, "command": cmd, "working_dir": cwd, "timeout": 30},
            )
            res = await mrs.wait_for_relay_response(
                db=db,
                user_id=user.id,
                req_id=req_id,
                timeout_seconds=20.0,
            )
            if res is None:
                res = {
                    "success": False,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Laptop did not respond. Ensure the backend daemon is running on your Windows laptop.",
                    "command": cmd,
                    "cwd": cwd or r"C:\kirtan\IRIS",
                }

        output = (res.get("stdout") or res.get("stderr") or "Command completed with no output.").strip()
        truncated_output = output[:2000] + ("\n... [output truncated]" if len(output) > 2000 else "")

        summary = (
            f"Executed `{cmd}` on laptop (Exit {res.get('returncode', 0)}):\n```\n{truncated_output}\n```"
            if res.get("success")
            else f"Command `{cmd}` failed (Exit {res.get('returncode', 0)}):\n{res.get('stderr')}"
        )

        return ToolResult(
            tool_name=self.name,
            success=res.get("success", False),
            data=res,
            summary=summary,
        )


class ListLaptopFilesParams(BaseModel):
    directory: str | None = Field(
        default=r"C:\kirtan\IRIS",
        description="Path of folder to list on laptop (defaults to 'C:\\kirtan\\IRIS')",
    )
    max_items: int = Field(default=40, ge=1, le=150, description="Max entries to return")


class ListLaptopFilesTool(Tool):
    name = "list_laptop_files"
    description = (
        "List files and directories on your Windows laptop. Use when user asks via voice or chat "
        "to list, surf, or browse files in a folder or repo (e.g. 'what files are in the project', 'surf files in backend', 'list files')."
    )
    parameters_schema = ListLaptopFilesParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        import os
        from pathlib import Path
        from app.services import mesh_relay_service as mrs

        folder = kwargs.get("directory") or r"C:\kirtan\IRIS"
        max_items = kwargs.get("max_items", 40)

        target = Path(folder)
        if not target.is_absolute():
            target = Path(r"C:\kirtan\IRIS") / folder

        if mrs.is_local_windows_host():
            if not target.exists():
                return ToolResult(tool_name=self.name, success=False, error=f"Directory '{target}' not found.", summary=f"Directory '{target}' does not exist.")
            
            entries = []
            try:
                for item in sorted(target.iterdir()):
                    entries.append({
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size_bytes": item.stat().st_size if item.is_file() else None,
                    })
                    if len(entries) >= max_items:
                        break
            except Exception as exc:
                return ToolResult(tool_name=self.name, success=False, error=str(exc), summary=f"Error reading directory: {exc}")
            
            file_names = [f"📁 {e['name']}/" if e["type"] == "directory" else f"📄 {e['name']}" for e in entries]
            summary = f"Found {len(entries)} items in `{target}`:\n" + "\n".join(file_names[:30])
            return ToolResult(tool_name=self.name, success=True, data={"directory": str(target), "entries": entries, "count": len(entries)}, summary=summary)
        else:
            ps_cmd = f"Get-ChildItem -Path '{target}' | Select-Object -First {max_items} Name, Mode, Length | Format-Table -AutoSize | Out-String"
            res = ms.execute_terminal_command(ps_cmd)
            return ToolResult(tool_name=self.name, success=res.get("success", False), data=res, summary=res.get("stdout") or "No files found.")


class ReadLaptopFileParams(BaseModel):
    file_path: str = Field(
        ...,
        description="Path of file to read (relative to 'C:\\kirtan\\IRIS' or absolute path, e.g. 'main.py' or 'backend/app/main.py')",
    )
    max_lines: int = Field(default=120, ge=1, le=500, description="Max lines to read")


class ReadLaptopFileTool(Tool):
    name = "read_laptop_file"
    description = (
        "Read and surf the text content of a file on your Windows laptop. "
        "Use when user asks to read, check, or surf a specific file (e.g. 'read main.py', 'surf requirements.txt', 'what is in README.md')."
    )
    parameters_schema = ReadLaptopFileParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from pathlib import Path
        from app.services import mesh_relay_service as mrs

        fpath = kwargs["file_path"].strip()
        max_lines = kwargs.get("max_lines", 120)

        target = Path(fpath)
        if not target.is_absolute():
            target = Path(r"C:\kirtan\IRIS") / fpath

        if mrs.is_local_windows_host():
            if not target.exists() or not target.is_file():
                return ToolResult(tool_name=self.name, success=False, error=f"File '{target}' not found.", summary=f"File '{target}' was not found.")
            
            try:
                lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
                preview = "\n".join(lines[:max_lines])
                total_lines = len(lines)
                summary = f"Read `{target.name}` ({min(len(lines), max_lines)} of {total_lines} lines):\n```\n{preview[:2500]}\n```"
                return ToolResult(tool_name=self.name, success=True, data={"file_path": str(target), "lines": total_lines, "content": preview}, summary=summary)
            except Exception as exc:
                return ToolResult(tool_name=self.name, success=False, error=str(exc), summary=f"Failed to read file: {exc}")
        else:
            res = ms.execute_terminal_command(f"Get-Content -Path '{target}' -Head {max_lines} | Out-String")
            return ToolResult(tool_name=self.name, success=res.get("success", False), data=res, summary=res.get("stdout") or res.get("stderr"))


class OpenLaptopFileParams(BaseModel):
    file_path: str = Field(
        ...,
        description="Path of file or folder to open on the laptop display",
    )
    application: str | None = Field(
        default="antigravity",
        description="Application to open with ('antigravity', 'vscode', 'explorer')",
    )


class OpenLaptopFileTool(Tool):
    name = "open_laptop_file"
    description = (
        "Open a file or folder on the Windows laptop screen in Antigravity IDE, VS Code, or File Explorer. "
        "Use when user asks to open a file in Antigravity or open a folder in Explorer on their laptop screen."
    )
    parameters_schema = OpenLaptopFileParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        fpath = kwargs["file_path"].strip()
        app = (kwargs.get("application") or "antigravity").lower()
        res = ms.launch_windows_app(app_name=app, argument=fpath)
        return ToolResult(tool_name=self.name, success=res.get("success", False), data=res, summary=res.get("message", f"Opened {fpath} in {app}."))


def mesh_tools() -> list[Tool]:
    """Factory returning all IRIS Mesh continuity tools."""
    return [
        RingMyPhoneTool(),
        LockWorkstationTool(),
        SyncClipboardTool(),
        GetDeviceMeshStatusTool(),
        LaunchLaptopAppTool(),
        RunLaptopTerminalCommandTool(),
        ListLaptopFilesTool(),
        ReadLaptopFileTool(),
        OpenLaptopFileTool(),
    ]

