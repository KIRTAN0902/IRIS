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


def launch_windows_app(app_name: str = "antigravity", argument: str | None = None) -> dict[str, Any]:
    """Launches or focuses a desktop application on the Windows laptop."""
    import os
    import shutil
    import subprocess
    from pathlib import Path

    app_clean = app_name.strip().lower().replace("-", "").replace(" ", "").replace("_", "")
    default_workspace = r"C:\kirtan\IRIS"
    user_home = Path.home()

    cmd: list[str] = []
    target_dir = argument or default_workspace

    # 1. Antigravity IDE / Antigravity
    if any(k in app_clean for k in ["antigravity", "agy"]):
        antigravity_candidates = [
            user_home / r"AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe",
            user_home / r"AppData\Local\Programs\Antigravity\Antigravity.exe",
            user_home / r"AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd",
            Path(r"C:\Users\shahk\AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe"),
            Path(r"C:\Users\shahk\AppData\Local\Programs\Antigravity\Antigravity.exe"),
            Path(r"C:\Users\shahk\AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd"),
        ]
        chosen = None
        for cand in antigravity_candidates:
            if cand.exists():
                chosen = str(cand)
                break

        if not chosen:
            chosen = shutil.which("antigravity.exe") or shutil.which("antigravity") or shutil.which("agy")

        if chosen:
            cmd = [chosen, target_dir]
        else:
            # Fallback to shell start
            cmd = ["cmd.exe", "/c", "start", "antigravity", target_dir]

    # 2. VS Code
    elif "vscode" in app_clean or "code" in app_clean:
        code_path = shutil.which("code.cmd") or shutil.which("code.exe") or shutil.which("code")
        if not code_path:
            cand = user_home / r"AppData\Local\Programs\Microsoft VS Code\Code.exe"
            if cand.exists():
                code_path = str(cand)
        if code_path:
            cmd = [code_path, target_dir]
        else:
            cmd = ["cmd.exe", "/c", "start", "code", target_dir]

    # 3. Terminal / PowerShell
    elif any(k in app_clean for k in ["terminal", "powershell", "pwsh", "wt", "cmd", "console"]):
        wt_candidates = [
            shutil.which("wt.exe"),
            shutil.which("wt"),
            user_home / r"AppData\Local\Microsoft\WindowsApps\wt.exe",
            Path(r"C:\Users\shahk\AppData\Local\Microsoft\WindowsApps\wt.exe"),
        ]
        wt_available = any(c and Path(c).exists() for c in wt_candidates)

        # On Windows, launching an interactive terminal from a background daemon requires 'cmd.exe /c start'
        # so the Windows Shell (Explorer) opens a real, visible foreground window on the active desktop.
        if wt_available and "powershell" not in app_clean and "cmd" not in app_clean:
            # Force a brand new window with '-w -1' so it never hides inside an invisible background tab
            cmd = ["cmd.exe", "/c", "start", "wt.exe", "-w", "-1", "-d", target_dir]
        else:
            sys_root = os.environ.get("SystemRoot", r"C:\Windows")
            ps_path = Path(sys_root) / r"System32\WindowsPowerShell\v1.0\powershell.exe"
            ps_bin = str(ps_path) if ps_path.exists() else "powershell.exe"
            cmd = ["cmd.exe", "/c", "start", ps_bin, "-NoExit", "-Command", f"Set-Location '{target_dir}'"]

    # 4. Chrome / Web Browser
    elif "chrome" in app_clean or "browser" in app_clean:
        cmd = ["explorer.exe", argument or "http://localhost:5173"]

    # 5. Explorer / Files
    elif "explorer" in app_clean or "files" in app_clean:
        cmd = ["explorer.exe", target_dir]

    # 6. Generic executable fallback
    else:
        cmd = ["cmd.exe", "/c", "start", app_name]
        if argument:
            cmd.append(argument)

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
        return {
            "success": True,
            "app": app_name,
            "pid": proc.pid,
            "command": cmd,
            "message": f"Successfully launched {app_name} on your Windows laptop.",
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

    # Intercept desktop GUI application launch shortcuts
    if lower_cmd in ["antigravity", "open antigravity", "launch antigravity", "agy ide", "antigravity ide"]:
        res = launch_windows_app("antigravity", argument=work_dir)
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

    # If user runs 'agy' alone without arguments, show helpful usage instead of hanging on interactive TUI
    if lower_cmd == "agy":
        return {
            "success": True,
            "returncode": 0,
            "stdout": (
                "⚡ Antigravity CLI (v1.3.3) is active on your Windows laptop!\n"
                "• Tap 'Open Antigravity IDE' above to open the full IDE on your laptop screen.\n"
                "• Or run instructions with: agy --help or agy -p \"your task prompt here\""
            ),
            "stderr": "",
            "command": clean_cmd,
            "cwd": work_dir,
            "elapsed_ms": 10,
        }

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
            "stdout": res.stdout,
            "stderr": res.stderr,
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


