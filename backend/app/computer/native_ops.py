"""Native Windows OS operations: PowerShell, process management, filesystem, and window control."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

from app.computer.session import KillSwitchTriggeredError, session_manager
from app.core.logging import get_logger

logger = get_logger("iris.computer.native_ops")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9
WM_CLOSE = 0x0010

_active_subprocesses: set[subprocess.Popen] = set()
_proc_lock = threading.Lock()
_INITIAL_DESKTOP: str | None = None

if os.name == "nt":
    try:
        _h_init = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        if _h_init:
            _buf = ctypes.create_unicode_buffer(256)
            if user32.GetUserObjectInformationW(_h_init, 2, _buf, 512, None) and _buf.value:
                _INITIAL_DESKTOP = _buf.value
    except Exception:
        pass


def _kill_all_subprocesses() -> None:
    """Callback triggered on emergency kill switch to terminate all active child processes immediately."""
    with _proc_lock:
        for p in list(_active_subprocesses):
            try:
                p.kill()
            except Exception:
                pass
        _active_subprocesses.clear()


session_manager.register_kill_callback(_kill_all_subprocesses)


def get_known_folder(name: str) -> Path:
    """Resolve standard Windows user folder paths."""
    userprofile = Path(os.environ.get("USERPROFILE", r"C:\Users\User"))
    name_low = name.lower().strip()
    if name_low in ("desktop", "my desktop"):
        return userprofile / "Desktop"
    if name_low in ("downloads", "download"):
        return userprofile / "Downloads"
    if name_low in ("documents", "docs"):
        return userprofile / "Documents"
    if name_low in ("pictures", "photos"):
        return userprofile / "Pictures"
    if name_low in ("workspace", "repo", "iris"):
        return Path(r"C:\kirtan\IRIS")
    return Path(name)


def ensure_interactive_desktop(desktop_name: str | None = None) -> bool:
    """Ensure current thread is attached to the interactive desktop without leaking handles."""
    if os.name != "nt":
        return False
    try:
        # 1. Attach process window station to WinSta0 if not already attached
        hwinsta_current = user32.GetProcessWindowStation()
        if hwinsta_current:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetUserObjectInformationW(hwinsta_current, 2, buf, 512, None)
            if buf.value.lower() != "winsta0":
                hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
                if hwinsta:
                    user32.SetProcessWindowStation(hwinsta)
        else:
            hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)

        # 2. If target desktop specified, attach directly
        if desktop_name:
            hdesk = user32.OpenDesktopW(desktop_name, 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
                return True

        # 3. Try OpenInputDesktop to attach to active user input desktop
        h_inp = user32.OpenInputDesktop(0, False, 0x01FF)
        if h_inp:
            ok = bool(user32.SetThreadDesktop(h_inp))
            return ok

        # 4. Fallback to 'Default'
        h_def = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if h_def:
            return bool(user32.SetThreadDesktop(h_def))
        return False
    except Exception as exc:
        logger.debug("Failed to attach to interactive desktop: %s", exc)
        return False


class NativeOps:
    """Provides direct, reliable operating system primitives for Windows."""

    # --- 1. Shell & PowerShell Execution ---
    @staticmethod
    def execute_powershell(
        command: str,
        cwd: str | Path | None = None,
        timeout_seconds: float = 30.0,
        max_output_chars: int = 10000,
    ) -> dict[str, Any]:
        """Execute a PowerShell command with strict timeout, directory control, and output bounding."""
        work_dir = str(get_known_folder(str(cwd))) if cwd else r"C:\kirtan\IRIS"
        if not os.path.exists(work_dir):
            work_dir = r"C:\kirtan\IRIS"

        # Check kill switch before launching
        if session_manager.is_kill_switch_engaged:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Aborted: Emergency kill-switch is engaged.",
                "duration_ms": 0,
                "cwd": work_dir,
            }

        # Safe UTF-8 output encoding wrapper
        ps_cmd = f"$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8; {command}"
        args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]

        start_time = time.perf_counter()
        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen(
                args,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            with _proc_lock:
                _active_subprocesses.add(proc)

            # Wait with active kill-switch monitoring and deadline
            poll_interval = 0.05
            deadline = start_time + timeout_seconds
            timed_out = False

            while True:
                if session_manager.is_kill_switch_engaged:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    with _proc_lock:
                        _active_subprocesses.discard(proc)
                    return {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": "Aborted: Emergency kill-switch triggered during execution.",
                        "duration_ms": int((time.perf_counter() - start_time) * 1000),
                        "cwd": work_dir,
                    }

                ret = proc.poll()
                if ret is not None:
                    break

                if time.perf_counter() > deadline:
                    timed_out = True
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    break

                time.sleep(poll_interval)

            stdout, stderr = proc.communicate()
            with _proc_lock:
                _active_subprocesses.discard(proc)

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            if timed_out:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Command timed out after {timeout_seconds}s.",
                    "duration_ms": duration_ms,
                    "cwd": work_dir,
                }

            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": (stdout or "").strip()[:max_output_chars],
                "stderr": (stderr or "").strip()[:max_output_chars],
                "duration_ms": duration_ms,
                "cwd": work_dir,
            }
        except Exception as exc:
            if proc:
                with _proc_lock:
                    _active_subprocesses.discard(proc)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Subprocess error: {exc}",
                "duration_ms": duration_ms,
                "cwd": work_dir,
            }

    # --- 2. Application Launching ---
    @staticmethod
    def launch_application(
        app_name_or_path: str,
        arguments: list[str] | str | None = None,
        working_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Launch a Windows desktop application."""
        raw = app_name_or_path.strip().lower()
        args = arguments if isinstance(arguments, list) else ([arguments] if arguments else [])

        # App alias registry
        app_map: dict[str, str] = {
            "notepad": "notepad.exe",
            "calc": "calc.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "paint": "mspaint.exe",
            "mspaint": "mspaint.exe",
            "cmd": "cmd.exe",
            "terminal": "wt.exe",
            "windows terminal": "wt.exe",
            "powershell": "powershell.exe",
            "code": "code.cmd",
            "vscode": "code.cmd",
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        }

        target = app_map.get(raw, app_name_or_path)
        cwd = str(get_known_folder(str(working_dir))) if working_dir else None

        cmd_list = [target] + [str(a) for a in args]
        try:
            si = subprocess.STARTUPINFO() if os.name == "nt" else None
            if si:
                si.lpDesktop = r"WinSta0\Default"
            # Use Popen to launch detached without blocking
            proc = subprocess.Popen(
                cmd_list,
                cwd=cwd,
                shell=False,
                startupinfo=si,
                creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
            )
            logger.info("Launched application '%s' (PID %d)", target, proc.pid)
            # Brief pause to allow window initialization
            time.sleep(0.5)
            return {
                "success": True,
                "pid": proc.pid,
                "app": target,
                "message": f"Successfully launched {target} (PID: {proc.pid})",
            }
        except FileNotFoundError:
            # Fallback using shell 'start'
            try:
                cmd_line = f'start "" "{target}" ' + " ".join(f'"{a}"' for a in args)
                res = NativeOps.execute_powershell(cmd_line, cwd=cwd)
                return {
                    "success": res["success"],
                    "app": target,
                    "message": f"Started {target} via shell: {res.get('stdout') or res.get('stderr')}",
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to launch application '{target}': {e}"}
        except Exception as exc:
            return {"success": False, "error": f"Failed to launch application '{target}': {exc}"}

    # --- 3. Window Enumeration & Management ---
    @staticmethod
    def list_windows(visible_only: bool = True, min_size: bool = True) -> list[dict[str, Any]]:
        """Enumerate top-level desktop windows across active, input, and default desktops."""
        if os.name != "nt":
            return []

        h_saved_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())

        # Collect candidate desktops to inspect
        desktops_to_check: list[str] = []
        try:
            if _INITIAL_DESKTOP and _INITIAL_DESKTOP not in desktops_to_check:
                desktops_to_check.append(_INITIAL_DESKTOP)
            h_curr = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            if h_curr:
                buf = ctypes.create_unicode_buffer(256)
                if user32.GetUserObjectInformationW(h_curr, 2, buf, 512, None) and buf.value:
                    if buf.value not in desktops_to_check:
                        desktops_to_check.append(buf.value)
            h_inp = user32.OpenInputDesktop(0, False, 0x01FF)
            if h_inp:
                buf = ctypes.create_unicode_buffer(256)
                if user32.GetUserObjectInformationW(h_inp, 2, buf, 512, None) and buf.value:
                    if buf.value not in desktops_to_check:
                        desktops_to_check.append(buf.value)
                user32.CloseDesktop(h_inp)
            if "Default" not in desktops_to_check:
                desktops_to_check.append("Default")
        except Exception:
            desktops_to_check = ["Default"]

        windows: list[dict[str, Any]] = []
        seen_hwnds: set[int] = set()
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        for d_name in desktops_to_check:
            hdesk = user32.OpenDesktopW(d_name, 0, False, 0x01FF)
            if not hdesk:
                continue
            user32.SetThreadDesktop(hdesk)

            def enum_proc(hwnd: int, lparam: int) -> bool:
                if hwnd in seen_hwnds:
                    return True
                if visible_only and not user32.IsWindowVisible(hwnd):
                    return True

                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True

                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()

                if not title:
                    return True

                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                width = rect.right - rect.left
                height = rect.bottom - rect.top

                if min_size and (width <= 10 or height <= 10):
                    return True

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                is_minimized = bool(user32.IsIconic(hwnd))
                is_maximized = bool(user32.IsZoomed(hwnd))

                seen_hwnds.add(hwnd)
                windows.append({
                    "hwnd": hwnd,
                    "title": title,
                    "pid": pid.value,
                    "desktop": d_name,
                    "rect": {
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom,
                        "width": width,
                        "height": height,
                    },
                    "is_minimized": is_minimized,
                    "is_maximized": is_maximized,
                })
                return True

            user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
            user32.CloseDesktop(hdesk)

        # Restore original thread desktop
        if h_saved_desktop:
            user32.SetThreadDesktop(h_saved_desktop)

        return windows

    @staticmethod
    def find_window(query: str, timeout_seconds: float = 2.0) -> dict[str, Any] | None:
        """Find a window by title substring (case-insensitive) or PID with retry for launch delay."""
        q_low = query.lower().strip()
        deadline = time.perf_counter() + max(0.2, timeout_seconds)

        while True:
            windows = NativeOps.list_windows(visible_only=True)
            # 1. Exact title match
            for w in windows:
                if w["title"].lower() == q_low:
                    return w
            # 2. Substring match
            for w in windows:
                if q_low in w["title"].lower():
                    return w
            # 3. Hidden or minimized windows search
            all_windows = NativeOps.list_windows(visible_only=False)
            for w in all_windows:
                if q_low in w["title"].lower():
                    return w

            if time.perf_counter() >= deadline:
                break
            time.sleep(0.3)

        return None

    @staticmethod
    def focus_window(hwnd_or_title: int | str) -> dict[str, Any]:
        """Bring window to foreground, restore if minimized, and set input focus."""
        desktop_target = None
        if isinstance(hwnd_or_title, str):
            win = NativeOps.find_window(hwnd_or_title)
            if not win:
                return {"success": False, "error": f"No window found matching '{hwnd_or_title}'"}
            hwnd = win["hwnd"]
            title = win["title"]
            desktop_target = win.get("desktop")
        else:
            hwnd = int(hwnd_or_title)
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value

        if not user32.IsWindow(hwnd):
            return {"success": False, "error": f"Invalid window handle {hwnd}"}

        # Attach to the window's desktop before focusing
        ensure_interactive_desktop(desktop_target)

        # Restore if minimized
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        # Force foreground attachment hack to ensure Windows switches focus
        current_thread_id = kernel32.GetCurrentThreadId()
        remote_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        user32.AttachThreadInput(current_thread_id, remote_thread_id, True)

        user32.ShowWindow(hwnd, SW_SHOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)

        user32.AttachThreadInput(current_thread_id, remote_thread_id, False)

        time.sleep(0.2)
        fg_hwnd = user32.GetForegroundWindow()
        is_focused = (fg_hwnd == hwnd)

        return {
            "success": True,
            "hwnd": hwnd,
            "title": title,
            "is_focused": is_focused,
        }

    @staticmethod
    def minimize_window(hwnd_or_title: int | str) -> dict[str, Any]:
        """Minimize a window."""
        ensure_interactive_desktop()
        win = NativeOps.find_window(hwnd_or_title) if isinstance(hwnd_or_title, str) else {"hwnd": int(hwnd_or_title)}
        if not win:
            return {"success": False, "error": f"Window not found: {hwnd_or_title}"}
        user32.ShowWindow(win["hwnd"], SW_MINIMIZE)
        return {"success": True, "hwnd": win["hwnd"]}

    @staticmethod
    def maximize_window(hwnd_or_title: int | str) -> dict[str, Any]:
        """Maximize a window."""
        ensure_interactive_desktop()
        win = NativeOps.find_window(hwnd_or_title) if isinstance(hwnd_or_title, str) else {"hwnd": int(hwnd_or_title)}
        if not win:
            return {"success": False, "error": f"Window not found: {hwnd_or_title}"}
        user32.ShowWindow(win["hwnd"], SW_MAXIMIZE)
        return {"success": True, "hwnd": win["hwnd"]}

    @staticmethod
    def close_window(hwnd_or_title: int | str) -> dict[str, Any]:
        """Gracefully close a window via WM_CLOSE."""
        ensure_interactive_desktop()
        win = NativeOps.find_window(hwnd_or_title) if isinstance(hwnd_or_title, str) else {"hwnd": int(hwnd_or_title)}
        if not win:
            return {"success": False, "error": f"Window not found: {hwnd_or_title}"}
        user32.PostMessageW(win["hwnd"], WM_CLOSE, 0, 0)
        return {"success": True, "hwnd": win["hwnd"]}

    # --- 4. Process Management ---
    @staticmethod
    def list_processes(filter_name: str | None = None) -> list[dict[str, Any]]:
        """List active processes with PID, name, and memory."""
        cmd = "Get-Process | Select-Object Id, ProcessName, WorkingSet64 | Sort-Object WorkingSet64 -Descending | Select-Object -First 30"
        if filter_name:
            cmd = f"Get-Process -Name '*{filter_name}*' -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, WorkingSet64"
        res = NativeOps.execute_powershell(f"{cmd} | ConvertTo-Json -Depth 2")
        if not res["success"] or not res["stdout"]:
            return []
        import json
        try:
            data = json.loads(res["stdout"])
            if isinstance(data, dict):
                data = [data]
            return [
                {
                    "pid": item.get("Id"),
                    "name": item.get("ProcessName"),
                    "memory_mb": round((item.get("WorkingSet64") or 0) / (1024 * 1024), 1),
                }
                for item in data
            ]
        except Exception:
            return []

    @staticmethod
    def kill_process(pid: int | None = None, name: str | None = None) -> dict[str, Any]:
        """Terminate a process safely by PID or name."""
        if pid:
            cmd = f"Stop-Process -Id {pid} -Force -ErrorAction Stop"
        elif name:
            cmd = f"Stop-Process -Name '{name}' -Force -ErrorAction Stop"
        else:
            return {"success": False, "error": "Either pid or name must be supplied"}
        res = NativeOps.execute_powershell(cmd)
        return {"success": res["success"], "message": "Process terminated" if res["success"] else res["stderr"]}

    # --- 5. Filesystem Operations ---
    @staticmethod
    def list_files(directory: str | Path | None = None) -> dict[str, Any]:
        """List directory contents with file sizes and types."""
        target = get_known_folder(str(directory)) if directory else Path(r"C:\kirtan\IRIS")
        if not target.exists():
            return {"success": False, "error": f"Directory not found: {target}"}

        entries = []
        try:
            for item in sorted(target.iterdir()):
                entries.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size_bytes": item.stat().st_size if item.is_file() else None,
                })
            return {"success": True, "path": str(target), "entries": entries}
        except Exception as exc:
            return {"success": False, "error": f"Failed to list directory: {exc}"}

    @staticmethod
    def read_file(file_path: str | Path, max_bytes: int = 500000) -> dict[str, Any]:
        """Read content of a text or markdown file."""
        target = Path(file_path)
        if not target.is_file():
            return {"success": False, "error": f"File not found: {target}"}
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "path": str(target), "content": content[:max_bytes]}
        except Exception as exc:
            return {"success": False, "error": f"Failed to read file: {exc}"}

    @staticmethod
    def create_file_or_dir(target_path: str | Path, content: str | None = None, is_dir: bool = False) -> dict[str, Any]:
        """Create a new file with text content or create a directory."""
        target = Path(target_path)
        try:
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                return {"success": True, "path": str(target), "type": "directory"}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content or "", encoding="utf-8")
            return {"success": True, "path": str(target), "type": "file", "bytes": len(content or "")}
        except Exception as exc:
            return {"success": False, "error": f"Failed to create file/dir: {exc}"}
