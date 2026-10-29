"""Windows process inspection and lifecycle management."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from app.core.logging import get_logger

logger = get_logger("iris.execution.windows.processes")

PROTECTED_PROCESSES = {
    "csrss.exe",
    "lsass.exe",
    "services.exe",
    "smss.exe",
    "svchost.exe",
    "system",
    "wininit.exe",
    "winlogon.exe",
    "explorer.exe",
}


class WindowsProcessManager:
    """Safely inspects running processes and TCP port listeners."""

    def list_processes(
        self,
        filter_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List running processes with PID, Name, and Memory usage."""
        try:
            cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                   "Get-Process | Select-Object -First " + str(limit) + " Id, ProcessName, WorkingSet64 | ConvertTo-Json -Compress"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0 or not res.stdout.strip():
                return []

            import json
            data = json.loads(res.stdout)
            if isinstance(data, dict):
                data = [data]

            results = []
            filter_lower = filter_name.lower().strip() if filter_name else None
            for p in data:
                name = str(p.get("ProcessName", ""))
                if filter_lower and filter_lower not in name.lower():
                    continue
                results.append({
                    "pid": p.get("Id"),
                    "name": name,
                    "memory_mb": round((p.get("WorkingSet64") or 0) / (1024 * 1024), 2),
                })
            return results
        except Exception as exc:
            logger.error("Failed to list processes: %s", exc)
            return []

    def inspect_port(self, port: int) -> dict[str, Any]:
        """Check if a local TCP port is active and identify its PID."""
        try:
            res = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            target = f":{port} "
            listening = False
            pids = []
            for line in res.stdout.splitlines():
                if target in line and "LISTENING" in line:
                    listening = True
                    parts = line.strip().split()
                    if parts:
                        pids.append(int(parts[-1]))

            return {
                "port": port,
                "listening": listening,
                "pids": list(set(pids)),
            }
        except Exception as exc:
            return {"port": port, "listening": False, "error": str(exc), "pids": []}

    def kill_process(self, pid: int | None = None, name: str | None = None) -> dict[str, Any]:
        """Terminate a user-level process by PID or name, rejecting critical system processes."""
        if not pid and not name:
            return {"success": False, "error": "Must specify either 'pid' or 'name'."}

        if name:
            name_clean = name.lower().strip()
            if not name_clean.endswith(".exe"):
                name_clean += ".exe"
            if name_clean in PROTECTED_PROCESSES:
                return {
                    "success": False,
                    "error": f"Refusing to terminate protected system process '{name}'.",
                }
            cmd = ["taskkill", "/F", "/T", "/IM", name_clean]
        else:
            cmd = ["taskkill", "/F", "/T", "/PID", str(pid)]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            success = res.returncode == 0
            return {
                "success": success,
                "exit_code": res.returncode,
                "output": (res.stdout or res.stderr).strip(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


process_manager = WindowsProcessManager()
