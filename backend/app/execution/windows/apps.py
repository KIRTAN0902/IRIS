"""Controlled Windows application launching."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.services import mesh_service as ms


class WindowsAppLauncher:
    """Manages launching approved desktop GUI applications and browsers."""

    def launch_app(
        self,
        app: str,
        argument: str | None = None,
        directory: str | None = None,
    ) -> dict[str, Any]:
        """Launch a desktop application with optional path or arguments."""
        clean_app = app.lower().strip()

        # 1. Specialized Chrome URL launcher
        if clean_app in ("chrome", "browser", "google-chrome"):
            url = argument or directory or "https://google.com"
            chrome_bin = (
                shutil.which("chrome.exe")
                or shutil.which("chrome")
                or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                or r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            )
            if Path(chrome_bin).exists():
                proc = subprocess.Popen([chrome_bin, url], shell=False)
                return {
                    "success": True,
                    "app": "Google Chrome",
                    "pid": proc.pid,
                    "url": url,
                    "message": f"Opened Chrome at {url}",
                }
            # Fallback to shell start
            proc = subprocess.Popen(["cmd.exe", "/c", "start", "", url], shell=False)
            return {
                "success": True,
                "app": "Default Browser",
                "pid": proc.pid,
                "url": url,
                "message": f"Opened default browser at {url}",
            }

        # 2. Leverage mesh_service's dynamic app index & window foregrounder
        return ms.launch_windows_app(
            app_name=app,
            argument=argument,
            directory=directory,
        )


app_launcher = WindowsAppLauncher()
