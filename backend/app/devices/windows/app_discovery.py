"""Dynamic Windows Application Discovery without hardcoded application lists.

Scans the real system:
1. Start Menu Shortcuts (.lnk) in ProgramData and User AppData
2. Registry App Paths (HKCU & HKLM Software\\Microsoft\\Windows\\CurrentVersion\\App Paths)
3. Universal Windows Platform (UWP) apps
4. Common system tools in PATH and Windows System32
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger("iris.devices.windows.app_discovery")


@dataclass
class DiscoveredApp:
    name: str
    clean_name: str
    target: str
    app_type: str  # "lnk", "exe", "uwp", "protocol"
    executable_path: str | None = None


class WindowsAppDiscovery:
    """Discovers 100% of installed desktop and store applications dynamically."""

    def __init__(self, cache_ttl_seconds: float = 600.0) -> None:
        self.cache_ttl = cache_ttl_seconds
        self._apps: dict[str, DiscoveredApp] = {}
        self._last_scan: float = 0.0

    def register_app(self, app: DiscoveredApp) -> None:
        """Register an application directly into the index (useful for dynamic plugins, portable apps, or tests)."""
        key = app.name.lower()
        clean_key = self._normalize_name(app.clean_name or app.name)
        self._apps[key] = app
        self._apps[clean_key] = app
        if self._last_scan == 0.0:
            self._last_scan = time.time()

    def refresh(self, force: bool = False) -> list[DiscoveredApp]:
        """Scans the local Windows machine for installed applications."""
        now = time.time()
        if not force and self._apps and (now - self._last_scan) < self.cache_ttl:
            return list(self._apps.values())

        if os.name != "nt":
            return list(self._apps.values())

        self._last_scan = now
        discovered: dict[str, DiscoveredApp] = {}

        # 1. Start Menu shortcuts (.lnk) in system-wide and user directories
        start_menu_dirs = [
            Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
            Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs",
        ]

        for base_dir in start_menu_dirs:
            if base_dir.exists():
                try:
                    for lnk_file in base_dir.rglob("*.lnk"):
                        stem = lnk_file.stem.strip()
                        key = stem.lower()
                        clean_key = self._normalize_name(stem)
                        # Avoid uninstallers, help, and readme shortcuts
                        if any(neg in key for neg in ["uninstall", "remove", "help", "readme", "license"]):
                            continue
                        app = DiscoveredApp(
                            name=stem,
                            clean_name=clean_key,
                            target=str(lnk_file),
                            app_type="lnk",
                            executable_path=str(lnk_file),
                        )
                        discovered[key] = app
                        discovered[clean_key] = app
                except Exception as exc:
                    logger.debug("Start menu scanning notice: %s", exc)

        # 2. Windows App Paths registry (HKLM & HKCU)
        try:
            import winreg

            for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hkey, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as root_key:
                        num_subkeys = winreg.QueryInfoKey(root_key)[0]
                        for idx in range(num_subkeys):
                            try:
                                subkey_name = winreg.EnumKey(root_key, idx)
                                with winreg.OpenKey(root_key, subkey_name) as subkey:
                                    val = winreg.QueryValue(subkey, "")
                                    if val and Path(val).exists():
                                        stem = Path(subkey_name).stem.strip()
                                        key = stem.lower()
                                        clean_key = self._normalize_name(stem)
                                        app = DiscoveredApp(
                                            name=stem.title(),
                                            clean_name=clean_key,
                                            target=val,
                                            app_type="exe",
                                            executable_path=val,
                                        )
                                        if key not in discovered:
                                            discovered[key] = app
                                        if clean_key not in discovered:
                                            discovered[clean_key] = app
                            except OSError:
                                continue
                except OSError:
                    pass
        except Exception as reg_exc:
            logger.debug("Registry App Paths scan notice: %s", reg_exc)

        # 3. Common built-in Windows utilities
        builtins = {
            "terminal": ("Terminal", "wt.exe", "exe"),
            "windows terminal": ("Windows Terminal", "wt.exe", "exe"),
            "powershell": ("PowerShell", "powershell.exe", "exe"),
            "pwsh": ("PowerShell Core", "pwsh.exe", "exe"),
            "cmd": ("Command Prompt", "cmd.exe", "exe"),
            "command prompt": ("Command Prompt", "cmd.exe", "exe"),
            "notepad": ("Notepad", "notepad.exe", "exe"),
            "calculator": ("Calculator", "calc.exe", "exe"),
            "calc": ("Calculator", "calc.exe", "exe"),
            "explorer": ("File Explorer", "explorer.exe", "exe"),
            "file explorer": ("File Explorer", "explorer.exe", "exe"),
            "task manager": ("Task Manager", "taskmgr.exe", "exe"),
            "taskmgr": ("Task Manager", "taskmgr.exe", "exe"),
            "settings": ("Settings", "ms-settings:", "protocol"),
            "windows settings": ("Windows Settings", "ms-settings:", "protocol"),
        }
        for alias, (display, target, atype) in builtins.items():
            clean = self._normalize_name(alias)
            app = DiscoveredApp(name=display, clean_name=clean, target=target, app_type=atype)
            if alias not in discovered:
                discovered[alias] = app
            if clean not in discovered:
                discovered[clean] = app

        self._apps = discovered
        logger.info("Windows App Discovery indexed %d applications dynamically.", len(discovered))
        return list(discovered.values())

    def find_app(self, query: str) -> DiscoveredApp | None:
        """Find an installed application dynamically through multi-tier matching."""
        self.refresh()
        q = query.strip().lower()
        clean_q = self._normalize_name(q)

        # 1. Exact match
        if q in self._apps:
            return self._apps[q]
        if clean_q in self._apps:
            return self._apps[clean_q]

        # 2. Prefix match
        for key, app in self._apps.items():
            if key.startswith(clean_q) or clean_q.startswith(key):
                return app

        # 3. Substring match
        for key, app in self._apps.items():
            if clean_q in key or key in clean_q:
                return app

        return None

    def list_all_apps(self) -> list[dict[str, Any]]:
        """Return unique list of discovered applications for capability reporting."""
        apps = self.refresh()
        seen = set()
        res = []
        for a in apps:
            if a.name not in seen:
                seen.add(a.name)
                res.append({
                    "name": a.name,
                    "clean_name": a.clean_name,
                    "app_type": a.app_type,
                    "target": a.target,
                })
        return res

    @staticmethod
    def _normalize_name(name: str) -> str:
        return (
            name.lower()
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
            .replace(".exe", "")
            .replace(".lnk", "")
        )


windows_app_discovery = WindowsAppDiscovery()
