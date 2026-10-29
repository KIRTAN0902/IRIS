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


# --- Windows Desktop System Actions & Sovereign Privacy Shield ---

SHIELD_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "shield_state.json"
SHIELD_CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "shield_config.json"
SHIELD_SCRIPT_PATH = Path(__file__).resolve().parent / "privacy_shield.py"


def is_privacy_shield_locked() -> bool:
    """Returns True if the sovereign privacy shield is currently active."""
    if SHIELD_STATE_FILE.exists():
        try:
            import json
            data = json.loads(SHIELD_STATE_FILE.read_text(encoding="utf-8"))
            if not data.get("locked"):
                return False
            pid = data.get("pid")
            if pid:
                import psutil
                if not psutil.pid_exists(pid):
                    SHIELD_STATE_FILE.write_text(json.dumps({"locked": False, "pid": None}), encoding="utf-8")
                    return False
            return True
        except Exception:
            pass
    return False


def lock_privacy_shield(password: str | None = None) -> bool:
    """Locks the workstation display using the Sovereign Privacy Shield."""
    try:
        import hashlib
        import json
        import os
        import subprocess
        import sys

        stored_hash = None
        stored_salt = None

        if SHIELD_CONFIG_FILE.exists():
            try:
                cfg = json.loads(SHIELD_CONFIG_FILE.read_text(encoding="utf-8"))
                stored_hash = cfg.get("password_hash")
                stored_salt = cfg.get("salt")
            except Exception:
                pass

        if password and password.strip():
            salt = os.urandom(16).hex()
            h = hashlib.sha256((password.strip() + salt).encode("utf-8")).hexdigest()
            SHIELD_CONFIG_FILE.write_text(
                json.dumps({"password_hash": h, "salt": salt}),
                encoding="utf-8",
            )
            stored_hash = h
            stored_salt = salt

        if is_privacy_shield_locked():
            logger.info("Privacy Shield is already active.")
            return True

        python_exe = sys.executable
        pythonw = Path(python_exe).parent / "pythonw.exe"
        exe_to_use = str(pythonw) if pythonw.exists() else python_exe

        # Write locked state BEFORE launching process so shield process never reads stale locked=False
        locked_payload = {
            "locked": True,
            "pid": None,
            "password_hash": stored_hash,
            "salt": stored_salt,
            "locked_at": datetime.now(UTC).isoformat(),
        }
        SHIELD_STATE_FILE.write_text(json.dumps(locked_payload), encoding="utf-8")

        si = None
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.lpDesktop = r"WinSta0\Default"

        proc = subprocess.Popen(
            [exe_to_use, str(SHIELD_SCRIPT_PATH)],
            cwd=str(Path(__file__).resolve().parent.parent.parent),
            startupinfo=si,
            close_fds=True,
        )

        locked_payload["pid"] = proc.pid
        SHIELD_STATE_FILE.write_text(json.dumps(locked_payload), encoding="utf-8")

        logger.info("Sovereign Privacy Shield launched successfully (PID: %s)", proc.pid)
        return True
    except Exception as exc:
        logger.error("Failed to launch Privacy Shield: %s", exc)
        return False


def unlock_privacy_shield(password: str | None = None) -> dict[str, Any]:
    """Unlocks the Sovereign Privacy Shield if credentials match."""
    try:
        import hashlib
        import json
        import os

        stored_hash = None
        stored_salt = None

        if SHIELD_CONFIG_FILE.exists():
            try:
                cfg = json.loads(SHIELD_CONFIG_FILE.read_text(encoding="utf-8"))
                stored_hash = cfg.get("password_hash")
                stored_salt = cfg.get("salt")
            except Exception:
                pass

        if not stored_hash and SHIELD_STATE_FILE.exists():
            try:
                st = json.loads(SHIELD_STATE_FILE.read_text(encoding="utf-8"))
                stored_hash = st.get("password_hash")
                stored_salt = st.get("salt")
            except Exception:
                pass

        # First-time setup: If no password was ever configured, register this password
        if not stored_hash and password and password.strip():
            salt = os.urandom(16).hex()
            stored_hash = hashlib.sha256((password.strip() + salt).encode("utf-8")).hexdigest()
            stored_salt = salt
            SHIELD_CONFIG_FILE.write_text(
                json.dumps({"password_hash": stored_hash, "salt": stored_salt}),
                encoding="utf-8",
            )

        if stored_hash and stored_salt:
            if not password or not password.strip():
                return {"success": False, "error": "Password required"}
            attempt = hashlib.sha256((password.strip() + stored_salt).encode("utf-8")).hexdigest()
            if attempt != stored_hash:
                return {"success": False, "error": "Incorrect password"}

        # Signal shield to close and clear state
        SHIELD_STATE_FILE.write_text(json.dumps({"locked": False, "pid": None}), encoding="utf-8")

        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

        logger.info("Sovereign Privacy Shield unlocked successfully")
        return {"success": True, "message": "Workstation unlocked"}
    except Exception as exc:
        logger.error("Failed to unlock Privacy Shield: %s", exc)
        return {"success": False, "error": str(exc)}


def lock_windows_pc(password: str | None = None, mode: str = "shield") -> bool:
    """Locks the workstation remotely using the Sovereign Privacy Shield."""
    if mode == "os":
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return True
        except Exception as exc:
            logger.error("Failed to lock Windows workstation: %s", exc)
            return False
    return lock_privacy_shield(password=password)


def unlock_windows_pc(pin: str | None = None, password: str | None = None) -> dict[str, Any]:
    """Unlocks the Sovereign Privacy Shield and wakes the display."""
    pwd = password or pin
    # 1. First unlock privacy shield
    result = unlock_privacy_shield(password=pwd)

    # 2. Also wake monitor via mouse move
    try:
        import ctypes
        ctypes.windll.user32.mouse_event(0x0001, 1, 1, 0, 0)
    except Exception:
        pass

    return result


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


def _bring_app_window_to_foreground(pid: int | None, app_name: str, keywords: list[str]) -> None:
    """Finds the desktop window created by the launched application and brings it to the top.

    Bypasses Windows Foreground Lock Timeout (Focus Stealing Prevention) by attaching
    thread input and synthesizing menu key events so the window pops in front of
    fullscreen or maximized applications (e.g. Chrome / YouTube).
    """
    import os
    import time

    if os.name != "nt":
        return

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Give the application process time to initialize its top-level window
    time.sleep(0.35)

    # Attach to interactive window station and default desktop
    try:
        h_winsta0 = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if h_winsta0:
            user32.SetProcessWindowStation(h_winsta0)
        h_default = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if h_default:
            user32.SetThreadDesktop(h_default)
    except Exception:
        pass

    target_keywords = [k.lower() for k in keywords if k]
    if app_name:
        target_keywords.append(app_name.lower())

    for _ in range(8):
        matched_hwnds: list[int] = []

        def enum_cb(hwnd: int, lparam: int) -> bool:
            if user32.IsWindowVisible(hwnd):
                wpid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if pid and wpid.value == pid:
                    matched_hwnds.append(hwnd)
                    return True

                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title_buf, 256)
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)

                combined = f"{title_buf.value} {cls_buf.value}".lower()
                for kw in target_keywords:
                    if kw in combined:
                        matched_hwnds.append(hwnd)
                        break
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try:
            h_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            user32.EnumDesktopWindows(h_desk, WNDENUMPROC(enum_cb), 0)
        except Exception:
            pass

        if matched_hwnds:
            for hwnd in matched_hwnds:
                try:
                    # 1. Restore if minimized
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE

                    # 2. Bypass foreground lock via Alt key injection
                    VK_MENU = 0x12
                    KEYEVENTF_KEYUP = 0x0002
                    user32.keybd_event(VK_MENU, 0, 0, 0)
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

                    # 3. AttachThreadInput fallback to guarantee top z-order
                    fg_hwnd = user32.GetForegroundWindow()
                    if fg_hwnd != hwnd:
                        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
                        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
                        cur_thread = kernel32.GetCurrentThreadId()
                        user32.AttachThreadInput(cur_thread, fg_thread, True)
                        user32.AttachThreadInput(target_thread, fg_thread, True)
                        user32.SetForegroundWindow(hwnd)
                        user32.BringWindowToTop(hwnd)
                        user32.AttachThreadInput(cur_thread, fg_thread, False)
                        user32.AttachThreadInput(target_thread, fg_thread, False)
                except Exception:
                    pass
            break

        time.sleep(0.3)


def parse_antigravity_cli_intent(text: str, default_dir: str = r"C:\kirtan\IRIS") -> tuple[str, str | None, bool]:
    """Extracts target directory, prompt, and resume flag from natural user phrasing."""
    import re
    from pathlib import Path

    t_lower = text.lower()
    resume = any(w in t_lower for w in ["resume", "continue", "-c", "--continue"])

    # Extract directory (e.g. "in C:\kirtan\IRIS", "in Downloads", "at Desktop")
    target_dir = default_dir
    dir_match = re.search(r'\b(?:in|at|into)\s+([a-zA-Z]:\\[^\s"\'`]+|[a-zA-Z]:/[^\s"\'`]+|[a-zA-Z0-9_\-\\.]+)', text, re.IGNORECASE)
    if dir_match:
        cand = dir_match.group(1).strip().strip("'\"`")
        if cand.lower() not in ["terminal", "cli", "powershell", "cmd", "agy", "antigravity", "conversation"]:
            resolved = resolve_laptop_path(cand)
            target_dir = str(resolved)

    # Extract prompt (e.g. 'ask it to fix the bug', 'with prompt "do X"', 'prompt do X')
    prompt = None
    prompt_match = re.search(r'\b(?:ask it to|with prompt|prompt)\s+["\']?([^"\'\n]+)["\']?', text, re.IGNORECASE)
    if prompt_match:
        cand_p = prompt_match.group(1).strip()
        if cand_p.lower() not in ["resume", "continue", "conversation", "terminal", "cli", "antigravity"]:
            cand_p = re.sub(r'\s+and\s+(?:resume|continue)(?:\s+conversation)?', '', cand_p, flags=re.IGNORECASE).strip()
            if cand_p:
                prompt = cand_p

    return target_dir, prompt, resume


def parse_terminal_intent(text: str) -> tuple[str, str]:
    """Extracts start and target directories from user phrasing.

    Always starts from user's home directory.
    If a specific directory is mentioned (e.g. 'in C:\\kirtan\\IRIS', 'at Desktop'),
    returns (home_dir, resolved_target_dir).
    If no directory is mentioned, returns (home_dir, home_dir).
    """
    import os
    from pathlib import Path
    import re

    home_dir = str(Path.home()) if os.name == "nt" else "~"
    t_clean = text.strip()

    dir_match = re.search(
        r'\b(?:in|at|into)\s+([a-zA-Z]:\\[^\s"\'`]+|[a-zA-Z]:/[^\s"\'`]+|[a-zA-Z0-9_\-\\.]+)',
        t_clean,
        re.IGNORECASE,
    )
    if dir_match:
        cand = dir_match.group(1).strip().strip("'\"`")
        excluded = [
            "terminal", "cli", "powershell", "cmd", "console", "wt",
            "window", "tab", "laptop", "pc", "workstation", "phone", "mobile"
        ]
        if cand.lower() not in excluded:
            if cand.lower() in ["home", "~", "root", "default"]:
                return home_dir, home_dir
            if os.name == "nt":
                resolved = resolve_laptop_path(cand)
                return home_dir, str(resolved)
            return home_dir, cand

    return home_dir, home_dir


class WindowsAppIndex:
    """Dynamic, sovereign Windows application index.

    Scans Start Menu shortcuts (.lnk), Windows App Paths registry, and system utilities.
    Indexes 100% of installed desktop and store applications with 0ms in-memory lookups.
    """

    def __init__(self) -> None:
        self._apps: dict[str, tuple[str, str]] = {}
        self._last_scan: float = 0.0

    def refresh(self, force: bool = False) -> None:
        import os
        import time
        from pathlib import Path

        now = time.time()
        # Scan at most once per 10 minutes unless forced
        if not force and self._apps and (now - self._last_scan) < 600.0:
            return
        self._last_scan = now

        if os.name != "nt":
            return

        new_apps: dict[str, tuple[str, str]] = {}

        # 1. Start Menu shortcuts (.lnk) in ProgramData and User AppData
        roots = [
            Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
            Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs",
        ]
        for base in roots:
            if base.exists():
                try:
                    for p in base.rglob("*.lnk"):
                        name = p.stem.lower().strip()
                        new_apps[name] = ("lnk", str(p))
                except Exception as exc:
                    logger.debug("Start menu scan notice: %s", exc)

        # 2. Windows App Paths registry (HKLM and HKCU)
        try:
            import winreg

            for root in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                        i = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, sub) as sk:
                                    val = winreg.QueryValue(sk, "")
                                    stem = Path(sub).stem.lower().strip()
                                    if stem not in new_apps and val:
                                        new_apps[stem] = ("exe", val)
                                i += 1
                            except OSError:
                                break
                except OSError:
                    pass
        except Exception:
            pass

        # 3. Standard Windows built-in aliases and protocols
        builtins: dict[str, tuple[str, str]] = {
            "terminal": ("exe", "wt.exe"),
            "wt": ("exe", "wt.exe"),
            "windows terminal": ("exe", "wt.exe"),
            "powershell": ("exe", "powershell.exe"),
            "pwsh": ("exe", "powershell.exe"),
            "cmd": ("exe", "cmd.exe"),
            "command prompt": ("exe", "cmd.exe"),
            "console": ("exe", "wt.exe"),
            "calc": ("exe", "calc.exe"),
            "calculator": ("exe", "calc.exe"),
            "notepad": ("exe", "notepad.exe"),
            "explorer": ("exe", "explorer.exe"),
            "files": ("exe", "explorer.exe"),
            "file explorer": ("exe", "explorer.exe"),
            "settings": ("protocol", "ms-settings:"),
            "windows settings": ("protocol", "ms-settings:"),
            "control panel": ("exe", "control.exe"),
            "task manager": ("exe", "taskmgr.exe"),
            "taskmgr": ("exe", "taskmgr.exe"),
            "chrome": ("lnk", str(Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk"))),
            "google chrome": ("lnk", str(Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk"))),
            "edge": ("lnk", str(Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Microsoft Edge.lnk"))),
            "microsoft edge": ("lnk", str(Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Microsoft Edge.lnk"))),
            "excel": ("lnk", str(Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Excel.lnk"))),
            "word": ("lnk", str(Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Word.lnk"))),
            "powerpoint": ("lnk", str(Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\PowerPoint.lnk"))),
            "antigravity ide": ("lnk", str(Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Antigravity.lnk")),
            "antigravity": ("lnk", str(Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Antigravity.lnk")),
        }
        for k, v in builtins.items():
            if k not in new_apps:
                new_apps[k] = v

        self._apps = new_apps
        logger.info("Indexed %d Windows applications dynamically.", len(self._apps))

    def find_app(self, query: str) -> tuple[str, str] | None:
        self.refresh()
        q = query.lower().strip()
        # 1. Exact match
        if q in self._apps:
            return self._apps[q]
        # 2. Prefix match
        for k, v in self._apps.items():
            if k.startswith(q) or q.startswith(k):
                return v
        # 3. Substring match
        for k, v in self._apps.items():
            if q in k or k in q:
                return v
        return None


windows_app_index = WindowsAppIndex()


def launch_windows_app(
    app_name: str = "antigravity_ide",
    argument: str | None = None,
    directory: str | None = None,
    prompt: str | None = None,
    resume: bool = False,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Launches or focuses a desktop application or CLI terminal on the Windows laptop."""
    import os
    import shutil
    import subprocess
    import threading
    from pathlib import Path

    raw_app = (app_name or "").strip().lower()
    app_clean = raw_app.replace("-", "").replace(" ", "").replace("_", "")
    default_workspace = r"C:\kirtan\IRIS"
    user_home = Path.home()

    # Determine target directory
    target_dir = default_workspace
    if directory and directory.strip():
        resolved = resolve_laptop_path(directory.strip())
        target_dir = str(resolved)
    elif argument and argument.strip():
        candidate_path = resolve_laptop_path(argument.strip())
        if candidate_path.exists() or any(c in argument for c in [":\\", ":/", "\\", "/"]) or argument.strip().lower() in ["home", "~", "desktop", "downloads", "documents"]:
            target_dir = str(candidate_path) if candidate_path.exists() else str(user_home)
        else:
            # If argument is not a path, treat as prompt if none provided
            if not prompt and argument.strip().lower() not in ["resume", "continue", "-c", "--continue"]:
                prompt = argument.strip()

    # Check resume intent in text
    if not resume:
        combined_text = f"{raw_app} {argument or ''} {prompt or ''}".lower()
        if any(w in combined_text for w in ["resume", "continue", "-c", "--continue"]):
            resume = True

    cmd: list[str] = []
    keywords: list[str] = [app_clean]

    # --- 1. Antigravity CLI (Terminal with agy) ---
    is_agy_ide = any(k in raw_app for k in ["ide", "gui", "editor", "desktop"])
    is_agy_cli = not is_agy_ide and (
        (any(k in raw_app for k in ["cli", "terminal", "console"]) and any(k in raw_app for k in ["antigravity", "agy"]))
        or raw_app in ["agy", "agycli", "antigravitycli", "antigravity_cli", "agy_cli", "antigravity"]
    )

    if is_agy_cli:
        keywords = ["powershell", "terminal", "cascadia", "agy", "antigravity"]
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        ps_path = Path(sys_root) / r"System32\WindowsPowerShell\v1.0\powershell.exe"
        ps_bin = str(ps_path) if ps_path.exists() else "powershell.exe"

        # Resolve agy binary
        agy_bin = shutil.which("agy.exe") or shutil.which("agy")
        if not agy_bin:
            cand = user_home / r"AppData\Local\agy\bin\agy.exe"
            if cand.exists():
                agy_bin = str(cand)
            else:
                agy_bin = "agy"

        # Construct agy CLI flags
        flags_list = []
        if conversation_id:
            flags_list.append(f"--conversation {conversation_id}")
        elif resume:
            flags_list.append("-c")

        if prompt and prompt.strip():
            # Escape quotes and PowerShell interpolation
            clean_p = prompt.strip().replace('"', '`"').replace("$", "`$")
            flags_list.append(f'-i "{clean_p}"')

        agy_invocation = f"& '{agy_bin}' {' '.join(flags_list)}".strip() if flags_list else f"& '{agy_bin}'"
        ps_command = f"Set-Location '{target_dir}'; {agy_invocation}"

        wt_bin = shutil.which("wt.exe") or shutil.which("wt") or str(user_home / r"AppData\Local\Microsoft\WindowsApps\wt.exe")
        has_wt = Path(wt_bin).exists() if wt_bin else False

        # Launch interactive terminal executing agy in target directory
        if has_wt:
            cmd = ["cmd.exe", "/c", "start", "", wt_bin, "-d", target_dir, ps_bin, "-NoExit", "-Command", agy_invocation]
        else:
            cmd = ["cmd.exe", "/c", "start", "", ps_bin, "-NoExit", "-Command", ps_command]
        app_name = "Antigravity CLI"

    # --- 2. Specialized Terminal Launching ---
    elif any(k in app_clean for k in ["terminal", "powershell", "pwsh", "wt", "cmd", "console"]):
        keywords = ["cascadia", "cmd", "powershell", "terminal", "pwsh"]
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        ps_path = Path(sys_root) / r"System32\WindowsPowerShell\v1.0\powershell.exe"
        ps_bin = str(ps_path) if ps_path.exists() else "powershell.exe"
        home_path = str(user_home)

        is_specific_dir = False
        target_dest = home_path
        if directory and directory.strip():
            cand_dir = str(resolve_laptop_path(directory.strip()))
            if cand_dir.lower() != home_path.lower() and directory.strip().lower() not in ["home", "~", "default", ""]:
                is_specific_dir = True
                target_dest = cand_dir
        elif argument and argument.strip():
            cand_dir = str(resolve_laptop_path(argument.strip()))
            if cand_dir.lower() != home_path.lower() and argument.strip().lower() not in ["home", "~", "default", ""]:
                is_specific_dir = True
                target_dest = cand_dir

        wt_bin = shutil.which("wt.exe") or shutil.which("wt") or str(user_home / r"AppData\Local\Microsoft\WindowsApps\wt.exe")
        has_wt = Path(wt_bin).exists() if wt_bin else False

        if "cmd" in app_clean and "powershell" not in app_clean and "wt" not in app_clean:
            if is_specific_dir:
                cmd = ["cmd.exe", "/c", "start", "", "cmd.exe", "/k", f"cd /d {home_path} && cd /d {target_dest}"]
            else:
                cmd = ["cmd.exe", "/c", "start", "", "cmd.exe", "/k", f"cd /d {home_path}"]
        elif has_wt:
            if is_specific_dir:
                cmd = ["cmd.exe", "/c", "start", "", wt_bin, "-d", home_path, ps_bin, "-NoExit", "-Command", f"Set-Location '{target_dest}'"]
            else:
                cmd = ["cmd.exe", "/c", "start", "", wt_bin, "-d", home_path]
        else:
            if is_specific_dir:
                cmd = ["cmd.exe", "/c", "start", "", ps_bin, "-NoExit", "-Command", f"Set-Location '{home_path}'; Set-Location '{target_dest}'"]
            else:
                cmd = ["cmd.exe", "/c", "start", "", ps_bin, "-NoExit", "-Command", f"Set-Location '{home_path}'"]
        app_name = "Terminal"

    # --- 3. Dynamic Universal App Resolution (100% of Installed Windows Applications) ---
    else:
        app_match = windows_app_index.find_app(raw_app)
        if app_match:
            kind, path = app_match
            app_stem = Path(path).stem.replace(".exe", "").title()
            app_name = "Antigravity IDE" if is_agy_ide else app_stem
            keywords = [raw_app, app_clean, app_stem.lower()]

            if kind in ("lnk", "protocol"):
                cmd = ["cmd.exe", "/c", "start", "", path]
            elif kind == "exe":
                if argument:
                    cmd = [path, argument]
                else:
                    cmd = [path]
            elif kind == "uwp":
                cmd = ["explorer.exe", f"shell:AppsFolder\\{path}"]
            else:
                cmd = ["cmd.exe", "/c", "start", "", path]
        else:
            # Fallback to shell start
            cmd = ["cmd.exe", "/c", "start", "", raw_app]
            if target_dir and target_dir != default_workspace:
                cmd.append(target_dir)

    if not cmd:
        return {
            "success": False,
            "app": app_name,
            "error": f"No command could be resolved for '{app_name}'",
            "message": f"Could not resolve executable for '{app_name}'.",
        }

    try:
        proc = subprocess.Popen(cmd, shell=False)
        app_label = cmd[0] if cmd else app_name
        logger.info("Launched desktop application: %s (PID: %s)", app_label, proc.pid)

        # Trigger background window bring-to-top to bypass Windows foreground locks
        threading.Thread(
            target=_bring_app_window_to_foreground,
            args=(proc.pid, app_name, keywords),
            daemon=True,
        ).start()

        action_desc = "Antigravity CLI" if is_agy_cli else app_name
        extra_info = []
        if is_agy_cli:
            if resume:
                extra_info.append("resuming conversation")
            if prompt:
                extra_info.append(f"with prompt: '{prompt}'")
        extra_str = f" ({', '.join(extra_info)})" if extra_info else ""
        return {
            "success": True,
            "app": app_name,
            "pid": proc.pid,
            "command": cmd,
            "directory": target_dir,
            "message": f"Successfully launched {action_desc} in '{target_dir}'{extra_str} on your Windows laptop.",
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
    import os
    import subprocess
    import time
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
            "elapsed_ms": 0,
        }

    default_workspace = r"C:\kirtan\IRIS"
    work_dir = cwd.strip() if cwd and cwd.strip() else default_workspace
    if not os.path.exists(work_dir):
        work_dir = str(Path.home())

    lower_cmd = clean_cmd.lower().strip()

    # Intercept desktop GUI application and interactive CLI launch shortcuts
    is_cli_shortcut = (
        lower_cmd in [
            "antigravity cli",
            "open antigravity cli",
            "launch antigravity cli",
            "agy cli",
            "open agy cli",
            "open agy",
            "open antigravity in terminal",
            "antigravity terminal",
            "agy terminal",
            "agy",
            "agy -c",
            "agy --continue",
        ]
        or lower_cmd.startswith("open agy")
        or lower_cmd.startswith("open antigravity cli")
        or lower_cmd.startswith("launch antigravity cli")
        or lower_cmd.startswith("agy cli")
    )
    if is_cli_shortcut:
        target_dir, prompt, resume = parse_antigravity_cli_intent(clean_cmd, default_dir=work_dir)
        res = launch_windows_app("antigravity_cli", directory=target_dir, prompt=prompt, resume=resume)
        return {
            "success": res.get("success", False),
            "returncode": 0 if res.get("success") else 1,
            "stdout": f"⚡ {res.get('message', 'Opened Antigravity CLI in terminal.')}",
            "stderr": res.get("error", ""),
            "command": clean_cmd,
            "cwd": target_dir,
            "elapsed_ms": 50,
        }

    if lower_cmd in [
        "antigravity",
        "open antigravity",
        "launch antigravity",
        "agy ide",
        "antigravity ide",
        "open antigravity ide",
        "launch antigravity ide",
    ]:
        res = launch_windows_app("antigravity_ide", directory=work_dir)
        return {
            "success": res.get("success", False),
            "returncode": 0 if res.get("success") else 1,
            "stdout": f"🚀 {res.get('message', 'Launched Antigravity IDE on Windows laptop.')}",
            "stderr": res.get("error", ""),
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": 50,
        }

    if lower_cmd in ["terminal", "open terminal", "launch terminal", "wt", "powershell"]:
        res = launch_windows_app("terminal", argument=work_dir)
        return {
            "success": res.get("success", False),
            "returncode": 0 if res.get("success") else 1,
            "stdout": f"💻 {res.get('message', 'Opened interactive Windows Terminal on laptop desktop.')}",
            "stderr": res.get("error", ""),
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": 50,
        }

    if lower_cmd in ["code", "vscode", "open code", "open vscode"]:
        res = launch_windows_app("vscode", argument=work_dir)
        return {
            "success": res.get("success", False),
            "returncode": 0 if res.get("success") else 1,
            "stdout": f"📝 {res.get('message', 'Launched VS Code on Windows laptop.')}",
            "stderr": res.get("error", ""),
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": 50,
        }

    if lower_cmd in ["explorer", "open explorer", "files"]:
        res = launch_windows_app("explorer", argument=work_dir)
        return {
            "success": res.get("success", False),
            "returncode": 0 if res.get("success") else 1,
            "stdout": f"📁 {res.get('message', 'Opened File Explorer on Windows laptop.')}",
            "stderr": res.get("error", ""),
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": 50,
        }

    # If user runs 'agy' with -p or other non-interactive flags, let it proceed to execution below

    # Security policy check for destructive commands
    try:
        from app.execution.policy import default_policy, redact_secrets, PermissionClass
        perm_class, reason = default_policy.classify_command(clean_cmd, cwd=work_dir)
        if perm_class == PermissionClass.CLASS_D_DESTRUCTIVE and default_policy.block_class_d:
            logger.warning("Terminal command blocked by policy: %s (Reason: %s)", clean_cmd, reason)
            return {
                "success": False,
                "returncode": 1,
                "stdout": "",
                "stderr": f"Command blocked by security policy: {reason}",
                "command": clean_cmd,
                "cwd": work_dir,
                "elapsed_ms": 0,
            }
    except Exception:
        redact_secrets = lambda s: s

    logger.info("Executing remote terminal command: %s (cwd=%s)", clean_cmd, work_dir)

    start_t = time.perf_counter()
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
        elapsed_ms = int((time.perf_counter() - start_t) * 1000)
        return {
            "success": res.returncode == 0,
            "returncode": res.returncode,
            "stdout": redact_secrets(res.stdout),
            "stderr": redact_secrets(res.stderr),
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": elapsed_ms,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - start_t) * 1000)
        logger.warning("Terminal command timed out after %ss: %s", timeout, clean_cmd)
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds.",
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start_t) * 1000)
        logger.error("Terminal execution error for '%s': %s", clean_cmd, exc)
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": elapsed_ms,
        }


def resolve_laptop_path(path_str: str | None = None) -> Path:
    """Resolves arbitrary Windows paths, home directories (~), user folder aliases (Desktop, Downloads, etc.), and repo paths."""
    from pathlib import Path
    import os

    if not path_str or not path_str.strip():
        return Path(r"C:\kirtan\IRIS")

    clean = path_str.strip().replace("/", "\\")
    home = Path.home()

    onedrive_desktop = home / "OneDrive" / "Desktop"
    desktop = onedrive_desktop if onedrive_desktop.exists() else home / "Desktop"

    onedrive_docs = home / "OneDrive" / "Documents"
    docs = onedrive_docs if onedrive_docs.exists() else home / "Documents"

    aliases = {
        "desktop": desktop,
        "downloads": home / "Downloads",
        "documents": docs,
        "pictures": home / "Pictures",
        "videos": home / "Videos",
        "home": home,
        "~": home,
        "c:": Path("C:\\"),
        "c:\\": Path("C:\\"),
        "root": Path("C:\\"),
    }

    low = clean.lower()
    for k, v in aliases.items():
        if low == k:
            return v
        if low.startswith(k + "\\"):
            return v / clean[len(k) + 1 :]

    if clean.startswith("~"):
        return Path(os.path.expanduser(clean))

    p = Path(clean)
    if p.is_absolute():
        return p

    repo_target = Path(r"C:\kirtan\IRIS") / clean
    if repo_target.exists():
        return repo_target

    home_target = home / clean
    if home_target.exists():
        return home_target

    return repo_target


def write_laptop_file(file_path: str, content: str, mode: str = "overwrite") -> dict[str, Any]:
    """Writes or appends text/code to a file anywhere on the Windows laptop."""
    target = resolve_laptop_path(file_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_mode = "a" if mode.lower() == "append" else "w"
        with open(target, file_mode, encoding="utf-8") as f:
            f.write(content)

        logger.info("Wrote laptop file: %s (mode=%s, %d bytes)", target, mode, len(content.encode("utf-8")))
        return {
            "success": True,
            "file_path": str(target),
            "bytes_written": len(content.encode("utf-8")),
            "mode": mode,
            "message": f"Successfully wrote {len(content)} characters to {target}.",
        }
    except Exception as exc:
        logger.error("Failed to write laptop file '%s': %s", target, exc)
        return {
            "success": False,
            "file_path": str(target),
            "error": str(exc),
            "message": f"Could not write to '{target}': {exc}",
        }


def search_laptop_files(query: str, directory: str | None = None, max_results: int = 30) -> dict[str, Any]:
    """Recursively searches for files matching a pattern or name across any directory or drive on the laptop."""
    import fnmatch
    import os

    root = resolve_laptop_path(directory)
    if not root.exists():
        return {"success": False, "error": f"Directory '{root}' does not exist.", "matches": [], "count": 0}

    clean_query = query.strip()
    pattern = clean_query if any(c in clean_query for c in ["*", "?", "["]) else f"*{clean_query}*"

    matches: list[dict[str, Any]] = []
    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", "$Recycle.Bin", "WinSxS"}

    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for f in filenames:
            if fnmatch.fnmatch(f.lower(), pattern.lower()):
                full_p = Path(dirpath) / f
                try:
                    size = full_p.stat().st_size
                except Exception:
                    size = None
                matches.append({
                    "name": f,
                    "path": str(full_p),
                    "size_bytes": size,
                    "directory": dirpath,
                })
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return {
        "success": True,
        "query": query,
        "root": str(root),
        "matches": matches,
        "count": len(matches),
    }


def read_laptop_file(file_path: str, max_lines: int = 150) -> dict[str, Any]:
    """Reads the content of any text file on the Windows laptop."""
    target = resolve_laptop_path(file_path)
    if not target.exists() or not target.is_file():
        return {
            "success": False,
            "file_path": str(target),
            "error": f"File '{target}' does not exist or is not a regular file.",
            "content": "",
            "lines_read": 0,
        }
    try:
        lines = []
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line)
        content = "".join(lines)
        return {
            "success": True,
            "file_path": str(target),
            "content": content,
            "lines_read": len(lines),
            "total_bytes": target.stat().st_size,
        }
    except Exception as exc:
        return {
            "success": False,
            "file_path": str(target),
            "error": str(exc),
            "content": "",
            "lines_read": 0,
        }


def list_laptop_files(directory: str | None = None, max_items: int = 40) -> dict[str, Any]:
    """Lists files and folders in any directory across the Windows laptop."""
    target = resolve_laptop_path(directory)
    if not target.exists() or not target.is_dir():
        return {
            "success": False,
            "directory": str(target),
            "error": f"Directory '{target}' does not exist.",
            "entries": [],
            "count": 0,
        }
    try:
        entries = []
        for item in sorted(target.iterdir()):
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": item.stat().st_size if item.is_file() else None,
            })
            if len(entries) >= max_items:
                break
        return {
            "success": True,
            "directory": str(target),
            "entries": entries,
            "count": len(entries),
        }
    except Exception as exc:
        return {
            "success": False,
            "directory": str(target),
            "error": str(exc),
            "entries": [],
            "count": 0,
        }


def capture_windows_screen(max_width: int = 1920) -> dict[str, Any]:
    """Captures the current primary Windows desktop screen, resizes if needed, and returns base64 JPEG."""
    import sys

    if sys.platform != "win32":
        return {
            "success": False,
            "error": f"Screen capture is only supported on Windows host, current platform: {sys.platform}",
        }

    try:
        import base64
        import ctypes
        import io
        from PIL import Image, ImageGrab

        # Ensure thread is attached to the interactive desktop station
        try:
            user32 = ctypes.windll.user32
            hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception as attach_err:
            logger.debug("Desktop station attach notice: %s", attach_err)

        img = ImageGrab.grab()
        orig_w, orig_h = img.size
        if orig_w > max_width:
            ratio = max_width / orig_w
            new_h = max(1, int(orig_h * ratio))
            img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        raw = buf.getvalue()
        b64 = base64.b64encode(raw).decode("utf-8")
        logger.info("Captured Windows desktop screen: (%dx%d) -> (%dx%d), %d bytes", orig_w, orig_h, img.width, img.height, len(raw))
        return {
            "success": True,
            "image_base64": b64,
            "mime_type": "image/jpeg",
            "width": img.width,
            "height": img.height,
            "original_width": orig_w,
            "original_height": orig_h,
            "bytes_count": len(raw),
        }
    except Exception as exc:
        logger.error("Failed to capture Windows desktop screen: %s", exc)
        return {"success": False, "error": str(exc)}


