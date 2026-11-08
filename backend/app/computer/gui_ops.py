"""Real-time Windows GUI automation: Mouse, keyboard, clipboard, and input synthesis."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import time
from typing import Any

import pyautogui
import pyperclip

from app.computer.native_ops import ensure_interactive_desktop
from app.computer.session import KillSwitchTriggeredError, session_manager
from app.core.logging import get_logger

logger = get_logger("iris.computer.gui_ops")

# Fail-safe: moving mouse to corner won't crash the daemon
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

user32 = ctypes.windll.user32

# Input injection constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Win32 Virtual Key Codes
VK_MAP = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "escape": 0x1B,
    "esc": 0x1B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    "capslock": 0x14,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


class GuiOps:
    """Provides high-fidelity, interactive Windows desktop GUI control."""

    # --- 1. Mouse Operations ---
    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        """Return primary screen resolution (width, height)."""
        ensure_interactive_desktop()
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        return (w, h)

    @staticmethod
    def get_mouse_position() -> tuple[int, int]:
        """Return current mouse pointer (x, y) coordinates."""
        ensure_interactive_desktop()
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    @staticmethod
    def move_mouse(x: int, y: int, duration: float = 0.15) -> dict[str, Any]:
        """Smoothly move mouse pointer to (x, y) screen coordinates."""
        sw, sh = GuiOps.get_screen_size()
        cx = max(0, min(sw - 1, int(x)))
        cy = max(0, min(sh - 1, int(y)))
        pyautogui.moveTo(cx, cy, duration=max(0.0, min(2.0, duration)))
        return {"success": True, "x": cx, "y": cy}

    @staticmethod
    def click(
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        clicks: int = 1,
    ) -> dict[str, Any]:
        """Click at (x, y) or at the current mouse position."""
        if x is not None and y is not None:
            GuiOps.move_mouse(x, y, duration=0.1)
        btn = button.lower().strip()
        if btn not in ("left", "right", "middle"):
            btn = "left"
        pyautogui.click(button=btn, clicks=max(1, min(5, clicks)))
        pos = GuiOps.get_mouse_position()
        return {"success": True, "clicked_at": {"x": pos[0], "y": pos[1]}, "button": btn, "clicks": clicks}

    @staticmethod
    def double_click(x: int | None = None, y: int | None = None) -> dict[str, Any]:
        """Double click at (x, y) or current position."""
        return GuiOps.click(x=x, y=y, button="left", clicks=2)

    @staticmethod
    def right_click(x: int | None = None, y: int | None = None) -> dict[str, Any]:
        """Right click at (x, y) or current position."""
        return GuiOps.click(x=x, y=y, button="right", clicks=1)

    @staticmethod
    def drag(from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.4) -> dict[str, Any]:
        """Drag mouse from (from_x, from_y) to (to_x, to_y)."""
        pyautogui.moveTo(from_x, from_y)
        time.sleep(0.05)
        pyautogui.dragTo(to_x, to_y, duration=duration, button="left")
        return {"success": True, "from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}

    @staticmethod
    def scroll(clicks: int = 3, direction: str = "down") -> dict[str, Any]:
        """Scroll vertical wheel (positive up, negative down)."""
        amount = -abs(clicks) if direction.lower() == "down" else abs(clicks)
        pyautogui.scroll(amount * 120)
        return {"success": True, "amount": amount}

    # --- 2. Keyboard Operations ---
    @staticmethod
    def type_unicode_char(char: str) -> None:
        """Type a single Unicode character using Win32 SendInput KEYEVENTF_UNICODE."""
        for code_unit in char.encode("utf-16le"):
            pass  # Handled below via ord
        code = ord(char)

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

        # Key down
        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)

        # Key up
        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

        inputs = (INPUT * 2)(inp_down, inp_up)
        user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

    @staticmethod
    def type_text(text: str, interval: float = 0.02, use_clipboard_fallback: bool = False) -> dict[str, Any]:
        """Type text into the currently active / focused application.
        
        Uses native Win32 Unicode input synthesis for character-exact fidelity,
        or clipboard paste for large multiline text blocks.
        """
        if not text:
            return {"success": True, "typed_chars": 0}

        # If text is very long or multiline, clipboard paste is 100x faster and safer
        if len(text) > 100 or "\n" in text or use_clipboard_fallback:
            prev_clip = ""
            try:
                prev_clip = pyperclip.paste()
            except Exception:
                pass

            try:
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.1)
                return {"success": True, "method": "clipboard_paste", "length": len(text)}
            finally:
                # Restore previous clipboard after a brief delay
                time.sleep(0.1)
                try:
                    if prev_clip and prev_clip != text:
                        pyperclip.copy(prev_clip)
                except Exception:
                    pass

        # Character-by-character typing with delay and active kill-switch check
        for ch in text:
            if session_manager.is_kill_switch_engaged:
                raise KillSwitchTriggeredError("Typing aborted: Emergency kill-switch engaged.")
            if ch == "\n" or ch == "\r":
                pyautogui.press("enter")
            elif ch == "\t":
                pyautogui.press("tab")
            else:
                try:
                    GuiOps.type_unicode_char(ch)
                except Exception:
                    pyautogui.write(ch)
            if interval > 0:
                time.sleep(interval)

        return {"success": True, "method": "unicode_keystrokes", "length": len(text)}

    @staticmethod
    def press_key(key: str) -> dict[str, Any]:
        """Press an individual key (e.g. 'enter', 'tab', 'escape', 'backspace', 'win')."""
        clean_key = key.lower().strip()
        if clean_key in ("win", "windows"):
            pyautogui.press("win")
        elif clean_key in VK_MAP:
            pyautogui.press(clean_key)
        else:
            pyautogui.press(clean_key)
        return {"success": True, "key": clean_key}

    @staticmethod
    def hotkey(*keys: str) -> dict[str, Any]:
        """Execute a keyboard shortcut combination (e.g. 'ctrl', 'c' or 'alt', 'tab')."""
        clean_keys = [k.lower().strip() for k in keys if k]
        if not clean_keys:
            return {"success": False, "error": "No keys supplied"}
        pyautogui.hotkey(*clean_keys)
        time.sleep(0.1)
        return {"success": True, "hotkey": "+".join(clean_keys)}

    # --- 3. Clipboard Operations ---
    @staticmethod
    def write_clipboard(text: str) -> dict[str, Any]:
        """Write text to the Windows system clipboard."""
        pyperclip.copy(text or "")
        return {"success": True, "length": len(text or "")}

    @staticmethod
    def read_clipboard() -> dict[str, Any]:
        """Read current text from the Windows system clipboard."""
        try:
            val = pyperclip.paste()
            return {"success": True, "text": val, "length": len(val)}
        except Exception as exc:
            return {"success": False, "error": f"Failed to read clipboard: {exc}"}

    @staticmethod
    def copy_selection() -> dict[str, Any]:
        """Send Ctrl+C to copy selected text in focused app and return the clipboard text."""
        # Clear clipboard temporarily to detect whether copy actually produced new text
        pyperclip.copy("")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        copied = pyperclip.paste()
        return {"success": bool(copied), "text": copied, "length": len(copied)}

    @staticmethod
    def paste_clipboard() -> dict[str, Any]:
        """Send Ctrl+V to paste the current clipboard into the focused app."""
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        return {"success": True}

    set_clipboard_text = write_clipboard
    get_clipboard_text = read_clipboard
