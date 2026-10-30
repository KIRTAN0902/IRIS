"""Dynamic Browser Discovery and Secure Website Navigation for Windows.

Discovers available browsers dynamically via Windows registry and provides
safe URL navigation with strict scheme validation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.logging import get_logger

logger = get_logger("iris.devices.windows.browser_discovery")

# Known online services mapped to their official URLs for browser fallback
COMMON_SERVICE_URLS: dict[str, str] = {
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "sheets": "https://sheets.google.com",
    "gmail": "https://mail.google.com",
    "google calendar": "https://calendar.google.com",
    "calendar": "https://calendar.google.com",
    "github": "https://github.com",
    "notion": "https://notion.so",
    "figma": "https://figma.com",
    "youtube": "https://youtube.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "linkedin": "https://linkedin.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
}


@dataclass
class DiscoveredBrowser:
    name: str
    executable_path: str
    is_default: bool = False


class WindowsBrowserDiscovery:
    """Discovers installed browsers and safely navigates to URLs."""

    def __init__(self) -> None:
        self._browsers: list[DiscoveredBrowser] = []
        self._last_scan: float = 0.0

    def discover_browsers(self, force: bool = False) -> list[DiscoveredBrowser]:
        """Discovers all installed browsers on the Windows system."""
        if not force and self._browsers:
            return self._browsers

        browsers: list[DiscoveredBrowser] = []
        seen_paths: set[str] = set()

        # 1. StartMenuInternet registry keys (HKLM & HKCU)
        if os.name == "nt":
            try:
                import winreg

                for root_hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        with winreg.OpenKey(root_hkey, r"SOFTWARE\Clients\StartMenuInternet") as key:
                            num_subkeys = winreg.QueryInfoKey(key)[0]
                            for i in range(num_subkeys):
                                try:
                                    b_name = winreg.EnumKey(key, i)
                                    with winreg.OpenKey(key, rf"{b_name}\shell\open\command") as cmd_key:
                                        raw_cmd = winreg.QueryValue(cmd_key, "")
                                        exe_path = raw_cmd.strip('"').split('"')[0].strip()
                                        if Path(exe_path).exists() and exe_path.lower() not in seen_paths:
                                            seen_paths.add(exe_path.lower())
                                            browsers.append(
                                                DiscoveredBrowser(
                                                    name=b_name.replace(".exe", "").title(),
                                                    executable_path=exe_path,
                                                )
                                            )
                                except OSError:
                                    continue
                    except OSError:
                        pass
            except Exception as reg_exc:
                logger.debug("Browser registry scan notice: %s", reg_exc)

        # 2. Check well-known browser locations if registry had none
        standard_checks = [
            ("Google Chrome", shutil.which("chrome.exe") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            ("Microsoft Edge", shutil.which("msedge.exe") or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            ("Brave", shutil.which("brave.exe") or str(Path.home() / r"AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe")),
            ("Mozilla Firefox", shutil.which("firefox.exe") or r"C:\Program Files\Mozilla Firefox\firefox.exe"),
        ]

        for name, path in standard_checks:
            if path and Path(path).exists() and path.lower() not in seen_paths:
                seen_paths.add(path.lower())
                browsers.append(DiscoveredBrowser(name=name, executable_path=str(path)))

        # Fallback to cmd/start default browser if nothing specific found
        if not browsers:
            browsers.append(DiscoveredBrowser(name="Default Browser", executable_path="explorer.exe", is_default=True))
        else:
            browsers[0].is_default = True

        self._browsers = browsers
        return browsers

    def get_preferred_browser(self) -> DiscoveredBrowser:
        """Returns the first available or default browser."""
        browsers = self.discover_browsers()
        for b in browsers:
            if b.is_default:
                return b
        return browsers[0]

    @staticmethod
    def resolve_service_destination(target: str) -> str | None:
        """Check if target corresponds to a known web service destination."""
        clean = target.lower().strip()
        return COMMON_SERVICE_URLS.get(clean)

    def open_url(self, url: str, browser_name: str | None = None) -> dict[str, Any]:
        """Validate URL scheme and open using an available browser on Windows."""
        clean_url = url.strip()
        parsed = urlparse(clean_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted.")

        browsers = self.discover_browsers()
        selected_browser: DiscoveredBrowser | None = None

        if browser_name:
            for b in browsers:
                if browser_name.lower() in b.name.lower():
                    selected_browser = b
                    break

        if not selected_browser:
            selected_browser = self.get_preferred_browser()

        try:
            if selected_browser.executable_path != "explorer.exe" and Path(selected_browser.executable_path).exists():
                proc = subprocess.Popen([selected_browser.executable_path, clean_url], shell=False)
            else:
                proc = subprocess.Popen(["cmd.exe", "/c", "start", "", clean_url], shell=False)

            return {
                "success": True,
                "browser": selected_browser.name,
                "url": clean_url,
                "pid": proc.pid,
                "message": f"Opened {clean_url} in {selected_browser.name}.",
            }
        except Exception as exc:
            logger.error("Failed to open URL %s: %s", clean_url, exc)
            return {
                "success": False,
                "browser": selected_browser.name if selected_browser else "Unknown",
                "url": clean_url,
                "error": str(exc),
                "message": f"Could not open URL: {exc}",
            }


windows_browser_discovery = WindowsBrowserDiscovery()
