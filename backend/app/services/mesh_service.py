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

# File Drop Storage Directory (uses /tmp on serverless Vercel)
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    STORAGE_DIR = Path("/tmp/mesh_vault")
else:
    STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "mesh_vault"

try:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


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


def unlock_windows_pc(pin: str | None = None) -> bool:
    """Wakes the Windows workstation, attaches to the active input desktop, and enters PIN/password."""
    try:
        import ctypes
        from ctypes import wintypes
        import time

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_ulong),
            ]

        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]

            _anonymous_ = ("_input",)
            _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]

        def send_vk(vk: int) -> None:
            inp = INPUT(type=1)
            inp.ki.wVk = vk
            inp.ki.dwFlags = 0
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.02)
            inp.ki.dwFlags = 0x0002  # KEYEVENTF_KEYUP
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        def send_unicode(char: str) -> None:
            inp = INPUT(type=1)
            inp.ki.wScan = ord(char)
            inp.ki.dwFlags = 0x0004  # KEYEVENTF_UNICODE
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.02)
            inp.ki.dwFlags = 0x0004 | 0x0002  # KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        # 1. Attach to active input desktop (handles Winlogon lock screen)
        try:
            import win32con
            import win32service

            hwinsta = win32service.OpenWindowStation("WinSta0", False, win32con.MAXIMUM_ALLOWED)
            hwinsta.SetProcessWindowStation()
            desk = win32service.OpenInputDesktop(0, False, win32con.MAXIMUM_ALLOWED)
            desk.SetThreadDesktop()
        except Exception as exc:
            logger.debug("Desktop switch notice: %s", exc)

        # 2. Wake monitor via mouse move
        ctypes.windll.user32.mouse_event(0x0001, 1, 1, 0, 0)
        time.sleep(0.15)

        # 3. Press Space and Enter to dismiss lock screen wallpaper
        send_vk(0x20)  # VK_SPACE
        time.sleep(0.1)
        send_vk(0x0D)  # VK_RETURN

        # 4. If password or PIN provided, type it and press Enter
        if pin:
            time.sleep(0.6)  # Allow slide-up animation to focus input box
            for char in str(pin):
                send_unicode(char)
                time.sleep(0.04)

            time.sleep(0.2)
            send_vk(0x0D)  # VK_RETURN

        logger.info("Successfully executed Windows unlock sequence")
        return True
    except Exception as exc:
        logger.error("Failed to unlock Windows workstation: %s", exc)
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


def launch_windows_app(app_name: str = "antigravity", argument: str | None = None) -> dict[str, Any]:
    """Launches or focuses a desktop application on the Windows laptop."""
    import subprocess
    from pathlib import Path

    app_clean = app_name.strip().lower()
    default_workspace = r"C:\kirtan\IRIS"

    antigravity_ide = r"C:\Users\shahk\AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe"
    antigravity_app = r"C:\Users\shahk\AppData\Local\Programs\Antigravity\Antigravity.exe"
    antigravity_cmd = r"C:\Users\shahk\AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd"

    cmd: list[str] = []

    if any(k in app_clean for k in ["antigravity", "agy", "anti-gravity"]):
        target = argument or default_workspace
        if os.path.exists(antigravity_ide):
            cmd = [antigravity_ide, target]
        elif os.path.exists(antigravity_app):
            cmd = [antigravity_app]
        elif os.path.exists(antigravity_cmd):
            cmd = [antigravity_cmd, target]
    elif "vscode" in app_clean or "code" in app_clean:
        cmd = ["code", argument or default_workspace]
    elif any(k in app_clean for k in ["terminal", "powershell", "wt", "cmd", "console"]):
        import shutil
        wt_path = shutil.which("wt.exe") or shutil.which("wt")
        target_dir = argument or default_workspace
        if wt_path:
            cmd = ["wt.exe", "-d", target_dir]
        else:
            cmd = ["powershell.exe", "-NoExit", "-Command", f"Set-Location '{target_dir}'"]
    elif "chrome" in app_clean or "browser" in app_clean:
        cmd = ["explorer.exe", argument or "http://localhost:5173"]
    else:
        cmd = [app_name]
        if argument:
            cmd.append(argument)

    try:
        proc = subprocess.Popen(cmd, shell=False)
        logger.info("Launched desktop application: %s (PID: %s)", cmd[0], proc.pid)
        return {
            "success": True,
            "app": app_name,
            "pid": proc.pid,
            "command": cmd,
            "message": f"Successfully launched {app_name} on Windows laptop.",
        }
    except Exception as exc:
        logger.error("Failed to launch application %s: %s", app_name, exc)
        return {
            "success": False,
            "app": app_name,
            "error": str(exc),
            "message": f"Could not launch {app_name}: {exc}",
        }


def execute_terminal_command(
    command: str,
    cwd: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Executes a PowerShell or shell CLI command on the Windows laptop remotely.

    Returns stdout, stderr, return code, and execution metadata.
    """
    import subprocess
    from pathlib import Path

    clean_cmd = command.strip()
    if not clean_cmd:
        return {
            "success": False,
            "returncode": 1,
            "stdout": "",
            "stderr": "Empty command provided.",
            "command": "",
            "cwd": "",
        }

    # If user runs 'agy' alone, append '--help' so it doesn't block on interactive TUI
    if clean_cmd.lower() == "agy":
        clean_cmd = "agy --help"

    default_workspace = r"C:\kirtan\IRIS"
    work_dir = cwd.strip() if cwd and cwd.strip() else default_workspace
    if not os.path.exists(work_dir):
        work_dir = str(Path.home())

    logger.info("Executing remote terminal command: %s (cwd=%s)", clean_cmd, work_dir)

    try:
        # Run command via PowerShell with utf-8 encoding and bounded execution timeout
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", clean_cmd],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "success": res.returncode == 0,
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "command": clean_cmd,
            "cwd": work_dir,
        }
    except subprocess.TimeoutExpired:
        logger.warning("Terminal command timed out after %ss: %s", timeout, clean_cmd)
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds.",
            "command": clean_cmd,
            "cwd": work_dir,
        }
    except Exception as exc:
        logger.error("Terminal execution error for '%s': %s", clean_cmd, exc)
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
            "command": clean_cmd,
            "cwd": work_dir,
        }

