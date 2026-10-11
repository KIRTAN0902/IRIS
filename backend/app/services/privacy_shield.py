"""IRIS Sovereign Privacy Shield: High-Security Fullscreen Workstation Lock.

Provides instant, 100% reliable remote lock and unlock across devices
without relying on kernel-restricted Winlogon injection.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tkinter as tk

STATE_FILE = Path(__file__).resolve().parent.parent.parent / "shield_state.json"
CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "shield_config.json"


def get_stored_credentials() -> tuple[str | None, str | None]:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data.get("password_hash"), data.get("salt")
        except Exception:
            pass
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return data.get("password_hash"), data.get("salt")
        except Exception:
            pass
    return None, None


def verify_pwd(pwd: str) -> bool:
    clean = pwd.strip()
    if not clean:
        return False
    h, salt = get_stored_credentials()
    if not h or not salt:
        # If no password has ever been set, save this password for subsequent unlocks
        salt = os.urandom(16).hex()
        h = hashlib.sha256((clean + salt).encode("utf-8")).hexdigest()
        CONFIG_FILE.write_text(json.dumps({"password_hash": h, "salt": salt}), encoding="utf-8")
        return True
    attempt = hashlib.sha256((clean + salt).encode("utf-8")).hexdigest()
    return attempt == h


class PrivacyShieldApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("IRIS Sovereign Shield")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#05070b")
        self.root.config(cursor="arrow")

        # Disable window close via Alt+F4
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.bind("<Escape>", lambda e: None)

        self._build_ui()
        try:
            st = {}
            if STATE_FILE.exists():
                st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            st["locked"] = True
            st["pid"] = os.getpid()
            STATE_FILE.write_text(json.dumps(st), encoding="utf-8")
        except Exception:
            pass
        self._poll_ipc_state()

    def _build_ui(self):
        container = tk.Frame(self.root, bg="#05070b")
        container.place(relx=0.5, rely=0.5, anchor="center")

        card = tk.Frame(
            container,
            bg="#0d1119",
            padx=40,
            pady=36,
            highlightthickness=1,
            highlightbackground="#1f293d",
        )
        card.pack()

        # Lock Icon & Brand
        icon_lbl = tk.Label(
            card,
            text="🔒",
            font=("Segoe UI Emoji", 36),
            bg="#0d1119",
            fg="#10b981",
        )
        icon_lbl.pack(pady=(0, 6))

        brand_lbl = tk.Label(
            card,
            text="IRIS SOVEREIGN SHIELD",
            font=("Segoe UI", 9, "bold"),
            bg="#0d1119",
            fg="#06b6d4",
        )
        brand_lbl.pack(pady=(0, 4))

        title_lbl = tk.Label(
            card,
            text="Workstation Locked Remotely",
            font=("Segoe UI", 16, "bold"),
            bg="#0d1119",
            fg="#f3f4f6",
        )
        title_lbl.pack(pady=(0, 8))

        sub_lbl = tk.Label(
            card,
            text="Authenticate on your paired phone to unlock seamlessly,\nor enter your password below.",
            font=("Segoe UI", 10),
            bg="#0d1119",
            fg="#9ca3af",
            justify="center",
        )
        sub_lbl.pack(pady=(0, 24))

        # Local Password Entry
        entry_frame = tk.Frame(card, bg="#0d1119")
        entry_frame.pack(fill="x", pady=(0, 8))

        self.pwd_entry = tk.Entry(
            entry_frame,
            show="•",
            font=("Segoe UI", 12),
            bg="#161b26",
            fg="#ffffff",
            insertbackground="#06b6d4",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#2d3748",
            highlightcolor="#06b6d4",
            width=26,
            justify="center",
        )
        self.pwd_entry.pack(ipady=7)
        self.pwd_entry.bind("<Return>", lambda e: self._attempt_unlock())
        self.pwd_entry.focus_set()

        self.error_lbl = tk.Label(
            card,
            text="",
            font=("Segoe UI", 9),
            bg="#0d1119",
            fg="#ef4444",
        )
        self.error_lbl.pack(pady=(0, 8))

        # Buttons
        btn_frame = tk.Frame(card, bg="#0d1119")
        btn_frame.pack(fill="x")

        unlock_btn = tk.Button(
            btn_frame,
            text="Unlock Workstation",
            font=("Segoe UI", 10, "bold"),
            bg="#10b981",
            fg="#ffffff",
            activebackground="#059669",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=18,
            pady=6,
            command=self._attempt_unlock,
        )
        unlock_btn.pack(fill="x")

    def _attempt_unlock(self):
        entered = self.pwd_entry.get().strip()
        if not entered:
            self.error_lbl.config(text="Please enter password.")
            return

        if verify_pwd(entered):
            self._close_shield()
        else:
            self.error_lbl.config(text="Incorrect password. Try again.")
            self.pwd_entry.delete(0, tk.END)

    def _poll_ipc_state(self):
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if data.get("locked") is False:
                    self._close_shield()
                    return
            except Exception:
                pass
        self.root.after(150, self._poll_ipc_state)

    def _close_shield(self):
        # Update state file
        try:
            STATE_FILE.write_text(json.dumps({"locked": False, "pid": None}), encoding="utf-8")
        except Exception:
            pass

        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

        self.root.destroy()
        sys.exit(0)


def main():
    root = tk.Tk()
    PrivacyShieldApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
