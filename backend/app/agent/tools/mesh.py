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
        default="antigravity_ide",
        description=(
            "Application or CLI to launch on the laptop. MUST be one of:\n"
            "- 'antigravity_cli': Launch Antigravity CLI in a terminal (opens terminal in requested directory, runs agy, supports prompt/resume).\n"
            "- 'antigravity_ide': Launch the full Antigravity IDE desktop GUI application.\n"
            "- 'terminal': Launch an interactive Windows Terminal / PowerShell window.\n"
            "- 'vscode': Launch Visual Studio Code.\n"
            "- 'explorer': Launch File Explorer.\n"
            "- 'chrome': Launch Google Chrome or web browser."
        ),
    )
    argument: str | None = Field(
        None,
        description="Optional folder, workspace path, URL, or CLI instruction.",
    )
    directory: str | None = Field(
        None,
        description="Directory or workspace path on the laptop to open the app or CLI in (e.g. 'C:\\kirtan\\IRIS', 'Desktop', 'Downloads', 'C:\\').",
    )
    prompt: str | None = Field(
        None,
        description="For Antigravity CLI: optional initial prompt or instruction to execute interactively (e.g. 'fix the auth bug').",
    )
    resume: bool = Field(
        default=False,
        description="For Antigravity CLI: set True to resume or continue the previous conversation (-c / --continue).",
    )
    conversation_id: str | None = Field(
        None,
        description="For Antigravity CLI: specific conversation ID to resume (--conversation <id>).",
    )


class LaunchLaptopAppTool(Tool):
    name = "launch_laptop_app"
    description = (
        "Launch or open a desktop application or interactive CLI on your Windows laptop remotely. "
        "Use 'antigravity_cli' when user asks for Antigravity CLI, agy, or terminal with antigravity (supports directory, prompt, and resume=True). "
        "Use 'antigravity_ide' when user asks for the Antigravity IDE GUI desktop app. "
        "Use 'terminal' for an interactive Windows Terminal/PowerShell window."
    )
    parameters_schema = LaunchAppParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs
        import secrets

        app_name = kwargs.get("app", "antigravity_ide")
        arg = kwargs.get("argument")
        directory = kwargs.get("directory")
        prompt = kwargs.get("prompt")
        resume = kwargs.get("resume", False)
        conversation_id = kwargs.get("conversation_id")

        # Normalize app name if user/model asks for 'antigravity cli' or 'agy cli'
        if any(k in app_name.lower() for k in ["cli", "terminal", "console"]) and any(k in app_name.lower() for k in ["antigravity", "agy"]):
            app_name = "antigravity_cli"
        elif app_name.lower().strip() in ["antigravity", "antigravity_ide", "agy_ide", "antigravity ide"]:
            app_name = "antigravity_ide"

        # Default terminal to user's home directory if not explicitly specified
        if any(k in app_name.lower() for k in ["terminal", "powershell", "cmd", "console", "wt"]) and app_name != "antigravity_cli":
            if not directory and (not arg or arg.strip().lower() in ["home", "~", "default", ""]):
                from pathlib import Path
                directory = str(Path.home())

        if mrs.is_local_windows_host():
            res = ms.launch_windows_app(
                app_name=app_name,
                argument=arg,
                directory=directory,
                prompt=prompt,
                resume=resume,
                conversation_id=conversation_id,
            )
        else:
            req_id = secrets.token_hex(6)
            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_voice_agent",
                target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                msg_type="REMOTE_COMMAND",
                payload={
                    "command": "LAUNCH_APP",
                    "app": app_name,
                    "argument": arg,
                    "directory": directory,
                    "prompt": prompt,
                    "resume": resume,
                    "conversation_id": conversation_id,
                    "req_id": req_id,
                },
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
                    "error": "Laptop workstation did not respond. Ensure the IRIS background daemon is running on your Windows laptop.",
                    "message": "Laptop workstation did not respond to the launch command.",
                }

        # Broadcast remote command to any connected WebSocket clients
        msg = ms.MeshMessage(
            type="REMOTE_COMMAND",
            sender_device="iris_agent",
            payload={
                "command": "LAUNCH_APP",
                "app": app_name,
                "argument": arg,
                "directory": directory,
                "prompt": prompt,
                "resume": resume,
                "conversation_id": conversation_id,
            },
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
        description="PowerShell or shell CLI command to execute on the laptop (e.g. 'git status', 'dir', 'npm test', 'tasklist', 'python script.py', 'pip install')",
    )
    working_dir: str | None = Field(
        default=None,
        description="Working directory or drive on the laptop to run the command in (e.g. 'Desktop', 'Downloads', 'C:\\kirtan\\IRIS', 'C:\\', or null for default repo)",
    )


class RunLaptopTerminalCommandTool(Tool):
    name = "run_laptop_terminal_command"
    description = (
        "Execute any terminal or PowerShell command on your Windows laptop with full system access and receive output. "
        "Use when user asks to run CLI commands, git operations, install packages, run scripts, check processes, or execute system tasks."
    )
    parameters_schema = RunTerminalCommandParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs
        import secrets

        cmd = kwargs["command"]
        raw_cwd = kwargs.get("working_dir")
        cwd = str(ms.resolve_laptop_path(raw_cwd)) if raw_cwd and raw_cwd.strip() else r"C:\kirtan\IRIS"

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
                    "cwd": cwd,
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
        default=None,
        description="Path of folder to list on laptop (e.g. 'Desktop', 'Downloads', 'Documents', 'C:\\', 'C:\\kirtan', or null for repo)",
    )
    max_items: int = Field(default=40, ge=1, le=150, description="Max entries to return")


class ListLaptopFilesTool(Tool):
    name = "list_laptop_files"
    description = (
        "List files and folders in any directory or drive across your Windows laptop. "
        "Use when user asks to list, surf, or browse files on Desktop, Downloads, project folders, or any drive."
    )
    parameters_schema = ListLaptopFilesParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs

        folder = kwargs.get("directory")
        target = ms.resolve_laptop_path(folder)
        max_items = kwargs.get("max_items", 40)

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
            import secrets
            req_id = secrets.token_hex(6)
            ps_cmd = f"Get-ChildItem -Path '{target}' | Select-Object -First {max_items} Name, Mode, Length | Format-Table -AutoSize | Out-String"
            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_voice_agent",
                target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                msg_type="TERMINAL_EXEC",
                payload={"req_id": req_id, "command": ps_cmd, "working_dir": r"C:\kirtan\IRIS", "timeout": 20},
            )
            res = await mrs.wait_for_relay_response(
                db=db,
                user_id=user.id,
                req_id=req_id,
                timeout_seconds=20.0,
            )
            if res is None:
                return ToolResult(tool_name=self.name, success=False, error="Laptop did not respond", summary="Laptop did not respond. Ensure the backend daemon is running on your Windows laptop.")
            return ToolResult(tool_name=self.name, success=res.get("success", False), data=res, summary=res.get("stdout") or res.get("stderr") or "No files found.")


class ReadLaptopFileParams(BaseModel):
    file_path: str = Field(
        ...,
        description="Path of file to read anywhere on the laptop (e.g. 'Desktop/todo.txt', 'main.py', 'C:\\notes.txt', 'Downloads/file.csv')",
    )
    max_lines: int = Field(default=150, ge=1, le=500, description="Max lines to read")


class ReadLaptopFileTool(Tool):
    name = "read_laptop_file"
    description = (
        "Read and surf the text content of any file on your Windows laptop. "
        "Use when user asks to read, inspect, or surf a file on Desktop, in projects, in Downloads, or anywhere on the laptop."
    )
    parameters_schema = ReadLaptopFileParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs

        fpath = kwargs["file_path"].strip()
        max_lines = kwargs.get("max_lines", 150)
        target = ms.resolve_laptop_path(fpath)

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
            import secrets
            req_id = secrets.token_hex(6)
            ps_cmd = f"Get-Content -Path '{target}' -Head {max_lines} | Out-String"
            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_voice_agent",
                target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                msg_type="TERMINAL_EXEC",
                payload={"req_id": req_id, "command": ps_cmd, "working_dir": r"C:\kirtan\IRIS", "timeout": 20},
            )
            res = await mrs.wait_for_relay_response(
                db=db,
                user_id=user.id,
                req_id=req_id,
                timeout_seconds=20.0,
            )
            if res is None:
                return ToolResult(tool_name=self.name, success=False, error="Laptop did not respond", summary="Laptop did not respond. Ensure the backend daemon is running on your Windows laptop.")
            return ToolResult(tool_name=self.name, success=res.get("success", False), data=res, summary=res.get("stdout") or res.get("stderr") or "No content.")


class WriteLaptopFileParams(BaseModel):
    file_path: str = Field(
        ...,
        description="Path of file to create or write anywhere on the laptop (e.g. 'Desktop/todo.txt', 'C:\\notes.md', 'scripts/test.py', 'Downloads/summary.txt')",
    )
    content: str = Field(
        ...,
        description="Text content or code to write into the file",
    )
    mode: str = Field(
        default="overwrite",
        description="'overwrite' to replace file content, or 'append' to add to existing file",
    )


class WriteLaptopFileTool(Tool):
    name = "write_laptop_file"
    description = (
        "Create, write, or append text or code to any file across your entire Windows laptop. "
        "Use when user asks to save notes, write code, create files, or modify files anywhere on their laptop."
    )
    parameters_schema = WriteLaptopFileParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs
        import secrets

        fpath = kwargs["file_path"].strip()
        content = kwargs["content"]
        mode = kwargs.get("mode", "overwrite")

        if mrs.is_local_windows_host():
            res = ms.write_laptop_file(file_path=fpath, content=content, mode=mode)
        else:
            req_id = secrets.token_hex(6)
            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_voice_agent",
                target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                msg_type="WRITE_FILE",
                payload={"req_id": req_id, "file_path": fpath, "content": content, "mode": mode},
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
                    "error": "Laptop did not respond. Ensure the backend daemon is running on your Windows laptop.",
                }

        summary = res.get("message") or ("Successfully wrote file." if res.get("success") else res.get("error", "Write failed."))
        return ToolResult(tool_name=self.name, success=res.get("success", False), data=res, summary=summary)


class SearchLaptopFilesParams(BaseModel):
    query: str = Field(
        ...,
        description="Filename or search pattern to locate on the laptop (e.g. '*.pdf', 'budget*', 'notes.txt', '*.py')",
    )
    directory: str | None = Field(
        default=None,
        description="Root folder or drive to search in (e.g. 'Desktop', 'Downloads', 'C:\\kirtan', 'C:\\', or null for repo)",
    )
    max_results: int = Field(default=25, ge=1, le=100, description="Max matches to return")


class SearchLaptopFilesTool(Tool):
    name = "search_laptop_files"
    description = (
        "Search and locate files across your entire Windows laptop by name or wildcard pattern (*.ext). "
        "Use when user asks to locate documents, find files on Desktop, in Downloads, or across drives."
    )
    parameters_schema = SearchLaptopFilesParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.services import mesh_relay_service as mrs
        import secrets

        query = kwargs["query"].strip()
        directory = kwargs.get("directory")
        max_results = kwargs.get("max_results", 25)

        if mrs.is_local_windows_host():
            res = ms.search_laptop_files(query=query, directory=directory, max_results=max_results)
        else:
            req_id = secrets.token_hex(6)
            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_voice_agent",
                target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                msg_type="SEARCH_FILES",
                payload={"req_id": req_id, "query": query, "directory": directory, "max_results": max_results},
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
                    "error": "Laptop did not respond. Ensure the backend daemon is running on your Windows laptop.",
                }

        matches = res.get("matches", [])
        if matches:
            file_list = [f"• `{m['name']}` ({m['path']})" for m in matches[:20]]
            summary = f"Found {len(matches)} matches for '{query}':\n" + "\n".join(file_list)
        else:
            summary = f"No files matching '{query}' found."

        return ToolResult(tool_name=self.name, success=res.get("success", False), data=res, summary=summary)


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
        from app.services import mesh_relay_service as mrs
        import secrets

        raw_fpath = kwargs["file_path"].strip()
        fpath = str(ms.resolve_laptop_path(raw_fpath))
        app = (kwargs.get("application") or "antigravity").lower()

        if mrs.is_local_windows_host():
            res = ms.launch_windows_app(app_name=app, argument=fpath)
        else:
            req_id = secrets.token_hex(6)
            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_voice_agent",
                target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                msg_type="REMOTE_COMMAND",
                payload={"command": "LAUNCH_APP", "app": app, "argument": fpath, "req_id": req_id},
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
                    "error": "Laptop did not respond. Ensure the IRIS background daemon is running on your Windows laptop.",
                }

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
        WriteLaptopFileTool(),
        SearchLaptopFilesTool(),
        OpenLaptopFileTool(),
    ]


