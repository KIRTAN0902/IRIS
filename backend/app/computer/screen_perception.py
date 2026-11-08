"""Screen observation, window inspection, and desktop perception engine."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import io
import os
import time
from typing import Any

import mss
from PIL import Image, ImageGrab
import win32con
import win32gui

from app.computer.native_ops import NativeOps, ensure_interactive_desktop
from app.core.logging import get_logger

logger = get_logger("iris.computer.screen_perception")

user32 = ctypes.windll.user32


class ScreenPerception:
    """Provides high-performance screen capture and window inspection primitives."""

    @staticmethod
    def capture_screenshot(
        output_path: str | None = None,
        max_width: int = 1920,
        monitor_index: int = 1,
        quality: int = 85,
    ) -> dict[str, Any]:
        """Capture the visible Windows desktop display as a base64-encoded JPEG image."""
        ensure_interactive_desktop()
        if isinstance(output_path, int):
            max_width = output_path
            output_path = None
        elif isinstance(max_width, str):
            output_path = max_width
            max_width = 1920

        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                mon = monitors[monitor_index] if monitor_index < len(monitors) else monitors[0]
                sct_img = sct.grab(mon)

                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                orig_w, orig_h = img.size

                if orig_w > max_width:
                    scale = max_width / float(orig_w)
                    new_h = max(1, int(orig_h * scale))
                    img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)

                if output_path:
                    from pathlib import Path
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    img.save(output_path, format="JPEG" if not output_path.endswith(".png") else "PNG", quality=quality)

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                raw_bytes = buffer.getvalue()
                b64 = base64.b64encode(raw_bytes).decode("utf-8")

                return {
                    "success": True,
                    "image_base64": b64,
                    "mime_type": "image/jpeg",
                    "width": img.width,
                    "height": img.height,
                    "original_width": orig_w,
                    "original_height": orig_h,
                    "bytes_count": len(raw_bytes),
                    "monitor_count": len(monitors) - 1,
                    "output_path": output_path,
                }
        except Exception as exc:
            logger.error("Screen capture failed: %s", exc)
            return {"success": False, "error": f"Screen capture error: {exc}"}

    capture_desktop = capture_screenshot

    @staticmethod
    def capture_window_screenshot(
        hwnd_or_title: int | str,
        quality: int = 85,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Capture a screenshot bounded strictly to a specific application window."""
        ensure_interactive_desktop()
        win = NativeOps.find_window(hwnd_or_title) if isinstance(hwnd_or_title, str) else {"hwnd": int(hwnd_or_title)}
        if not win or not win.get("hwnd"):
            return {"success": False, "error": f"Window not found: {hwnd_or_title}"}

        hwnd = win["hwnd"]
        try:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            bbox = (rect.left, rect.top, rect.right, rect.bottom)
            if rect.right <= rect.left or rect.bottom <= rect.top:
                return {"success": False, "error": "Window has non-positive geometry"}

            img = ImageGrab.grab(bbox=bbox)
            if output_path:
                img.save(output_path, format="JPEG" if not output_path.endswith(".png") else "PNG", quality=quality)

            buffer = io.BytesIO()
            img.convert("RGB").save(buffer, format="JPEG", quality=quality)
            raw_bytes = buffer.getvalue()
            b64 = base64.b64encode(raw_bytes).decode("utf-8")

            return {
                "success": True,
                "hwnd": hwnd,
                "title": win.get("title", ""),
                "image_base64": b64,
                "mime_type": "image/jpeg",
                "width": img.width,
                "height": img.height,
                "output_path": output_path,
            }
        except Exception as exc:
            return {"success": False, "error": f"Failed to capture window {hwnd}: {exc}"}

    capture_window = capture_window_screenshot

    @staticmethod
    def read_window_text(hwnd_or_title: int | str) -> dict[str, Any]:
        """Inspect and extract visible text from a window's controls and child elements."""
        win = NativeOps.find_window(hwnd_or_title) if isinstance(hwnd_or_title, str) else {"hwnd": int(hwnd_or_title)}
        if not win or not win.get("hwnd"):
            return {"success": False, "error": f"Window not found: {hwnd_or_title}"}

        hwnd = win["hwnd"]
        found_texts: list[str] = []

        def enum_child(child_hwnd: int, lparam: int) -> bool:
            # Check length via WM_GETTEXTLENGTH
            length = win32gui.SendMessage(child_hwnd, win32con.WM_GETTEXTLENGTH, 0, 0)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 2)
                user32.SendMessageW(child_hwnd, win32con.WM_GETTEXT, length + 1, ctypes.byref(buf))
                txt = buf.value.strip()
                if txt and txt not in found_texts:
                    found_texts.append(txt)
            else:
                txt = win32gui.GetWindowText(child_hwnd).strip()
                if txt and txt not in found_texts:
                    found_texts.append(txt)
            return True

        try:
            win32gui.EnumChildWindows(hwnd, enum_child, 0)
        except Exception:
            pass

        return {
            "success": True,
            "hwnd": hwnd,
            "title": win.get("title", ""),
            "extracted_texts": found_texts,
            "full_text": "\n".join(found_texts),
        }

    @staticmethod
    def _verify_via_uia(hwnd: int, expected_snippet: str) -> bool:
        """Inspect window elements via Windows UI Automation without touching clipboard or cursor selection."""
        if os.name != "nt" or not hwnd:
            return False
        try:
            import subprocess
            # Escape expected text for regex matching in powershell
            clean_expected = expected_snippet.strip().replace("'", "''").replace('"', '`"')
            ps_script = f"""
Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue
try {{
    $elem = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{hwnd})
    if ($elem) {{
        $cond = [System.Windows.Automation.Condition]::TrueCondition
        $children = $elem.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
        foreach ($c in $children) {{
            try {{
                $tp = $c.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
                if ($tp -and ($tp.DocumentRange.GetText(-1) -match [regex]::Escape('{clean_expected}'))) {{
                    Write-Output "UIA_MATCH"
                    exit 0
                }}
            }} catch {{}}
            try {{
                $vp = $c.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ($vp -and ($vp.Current.Value -match [regex]::Escape('{clean_expected}'))) {{
                    Write-Output "UIA_MATCH"
                    exit 0
                }}
            }} catch {{}}
        }}
    }}
}} catch {{}}
"""
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=3.5,
            )
            return "UIA_MATCH" in (res.stdout or "")
        except Exception as exc:
            logger.debug("UIA text inspection exception: %s", exc)
            return False

    @staticmethod
    def verify_window_text_contains(hwnd_or_title: int | str, expected_snippet: str) -> dict[str, Any]:
        """Verify whether an application window contains an expected text substring.
        
        Uses non-invasive methods exclusively: child control inspection, UI Automation
        Text/Value patterns, and window title checks. Never alters user cursor, selection,
        or clipboard state.
        """
        win = NativeOps.find_window(hwnd_or_title) if isinstance(hwnd_or_title, str) else {"hwnd": int(hwnd_or_title)}
        if not win:
            return {"success": False, "verified": False, "error": f"Window '{hwnd_or_title}' not found"}

        hwnd = win["hwnd"]
        expected = expected_snippet.strip().lower()

        # 1. Child control inspection via WM_GETTEXT
        res = ScreenPerception.read_window_text(hwnd)
        full_text = res.get("full_text", "").lower()
        if expected in full_text:
            return {
                "success": True,
                "verified": True,
                "method": "child_controls_inspection",
                "matched_text": expected_snippet,
                "hwnd": hwnd,
                "title": win.get("title"),
            }

        # 2. Window title check
        if expected in win.get("title", "").lower():
            return {
                "success": True,
                "verified": True,
                "method": "window_title",
                "matched_text": expected_snippet,
                "hwnd": hwnd,
                "title": win.get("title"),
            }

        # 3. Non-invasive UI Automation inspection (reads TextPattern / ValuePattern in-place)
        if ScreenPerception._verify_via_uia(hwnd, expected_snippet):
            return {
                "success": True,
                "verified": True,
                "method": "ui_automation_inspection",
                "matched_text": expected_snippet,
                "hwnd": hwnd,
                "title": win.get("title"),
            }

        return {
            "success": True,
            "verified": False,
            "error": f"Text '{expected_snippet}' was not confirmed in window '{win.get('title')}'",
            "hwnd": hwnd,
        }
