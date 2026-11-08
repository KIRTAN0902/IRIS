"""Command Line Interface for IRIS Computer Control.

Allows direct terminal execution of desktop automation, inspection,
and session management operations on the local Windows machine.

Usage:
    python -m app.computer.cli status
    python -m app.computer.cli session start [--ttl-seconds 300]
    python -m app.computer.cli session stop
    python -m app.computer.cli session pause
    python -m app.computer.cli session resume
    python -m app.computer.cli kill
    python -m app.computer.cli run "<instruction>"
    python -m app.computer.cli launch <app_name>
    python -m app.computer.cli windows
    python -m app.computer.cli focus <title_or_hwnd>
    python -m app.computer.cli click <x> <y> [--button left|right|double]
    python -m app.computer.cli type "<text>"
    python -m app.computer.cli screenshot [--window <title>] [--output <path>]
    python -m app.computer.cli clipboard get|set "<text>"
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.computer.contracts import ComputerAction, ComputerActionType, ComputerTaskRequest
from app.computer.engine import computer_engine
from app.computer.gui_ops import GuiOps
from app.computer.native_ops import NativeOps
from app.computer.screen_perception import ScreenPerception
from app.computer.session import session_manager


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_status(_args: argparse.Namespace) -> int:
    status = session_manager.get_info().to_dict()
    _print_json(status)
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    sub = args.session_action
    if sub == "start":
        mins = max(1, args.ttl_seconds // 60)
        session = session_manager.activate_session(
            reason=args.purpose or "CLI interactive session",
            expiry_minutes=mins,
            authorized_by="cli_user",
        )
        print(f"[OK] Session activated. ID: {session.session_id}, State: {session.state.value}")
        return 0
    elif sub == "stop":
        session_manager.terminate_session("User stopped session via CLI")
        print("[OK] Session terminated. Subsystem returned to BACKGROUND mode.")
        return 0
    elif sub == "pause":
        session_manager.pause_session("User paused session via CLI")
        print("[OK] Session paused.")
        return 0
    elif sub == "resume":
        session_manager.resume_session()
        print("[OK] Session resumed to ACTIVE.")
        return 0
    elif sub == "reset":
        session_manager.reset_kill_switch()
        print("[OK] Kill switch reset. Subsystem returned to BACKGROUND mode.")
        return 0
    else:
        print(f"[ERROR] Unknown session action: {sub}", file=sys.stderr)
        return 1


def cmd_kill(args: argparse.Namespace) -> int:
    if getattr(args, "reset", False):
        session_manager.reset_kill_switch()
        print("[OK] Emergency Kill-Switch reset. Subsystem in BACKGROUND mode.")
        return 0
    session_manager.trigger_kill_switch("EMERGENCY KILL SWITCH TRIGGERED VIA CLI")
    print("[CRITICAL] Emergency Kill-Switch triggered. All sessions terminated, input blocked.")
    return 0



def cmd_run(args: argparse.Namespace) -> int:
    instruction = args.instruction
    print(f"[*] Executing instruction: '{instruction}'...")
    req = ComputerTaskRequest(
        instruction=instruction,
        auto_activate=args.auto_activate,
        max_steps=args.max_steps,
    )
    result = computer_engine.execute_task(req)
    _print_json(result.to_dict())
    return 0 if result.success else 1


def cmd_launch(args: argparse.Namespace) -> int:
    res = NativeOps.launch_application(args.app_name, args.arguments)
    _print_json(res)
    return 0 if res.get("success") else 1


def cmd_windows(_args: argparse.Namespace) -> int:
    wins = NativeOps.list_windows(visible_only=True)
    _print_json(wins)
    return 0


def cmd_focus(args: argparse.Namespace) -> int:
    target = args.target
    if target.isdigit():
        hwnd = int(target)
    else:
        win = NativeOps.find_window(target)
        if not win:
            print(f"[ERROR] Could not find window matching '{target}'", file=sys.stderr)
            return 1
        hwnd = win["hwnd"]

    success = NativeOps.focus_window(hwnd)
    print(f"Focus window {hwnd}: {'SUCCESS' if success else 'FAILED'}")
    return 0 if success else 1


def cmd_click(args: argparse.Namespace) -> int:
    action = ComputerAction(
        action_type=ComputerActionType.MOUSE_CLICK,
        params={
            "x": args.x,
            "y": args.y,
            "button": args.button,
            "clicks": 2 if args.button == "double" else 1,
        },
    )
    res = computer_engine.execute_action(action)
    _print_json(res.to_dict())
    return 0 if res.success else 1


def cmd_type(args: argparse.Namespace) -> int:
    action = ComputerAction(
        action_type=ComputerActionType.KEYBOARD_TYPE,
        params={"text": args.text},
    )
    res = computer_engine.execute_action(action)
    _print_json(res.to_dict())
    return 0 if res.success else 1


def cmd_screenshot(args: argparse.Namespace) -> int:
    if args.window:
        win = NativeOps.find_window(args.window)
        if not win:
            print(f"[ERROR] Window matching '{args.window}' not found", file=sys.stderr)
            return 1
        res = ScreenPerception.capture_window(win["hwnd"], output_path=args.output)
    else:
        res = ScreenPerception.capture_desktop(output_path=args.output)
    _print_json(res)
    return 0 if res.get("success") else 1


def cmd_clipboard(args: argparse.Namespace) -> int:
    sub = args.clipboard_action
    if sub == "get":
        text = GuiOps.get_clipboard_text()
        print(text)
        return 0
    elif sub == "set":
        text = args.text or ""
        success = GuiOps.set_clipboard_text(text)
        print(f"Set clipboard: {'SUCCESS' if success else 'FAILED'}")
        return 0 if success else 1
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.computer.cli",
        description="IRIS Windows Computer Control CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # status
    subparsers.add_parser("status", help="Get current session and capability status")

    # session
    p_session = subparsers.add_parser("session", help="Manage computer control sessions")
    p_session.add_argument("session_action", choices=["start", "stop", "pause", "resume", "reset"])
    p_session.add_argument("--purpose", help="Reason for session activation", default="Interactive CLI")
    p_session.add_argument("--ttl-seconds", type=int, default=300, help="Inactivity timeout in seconds")

    # kill
    p_kill = subparsers.add_parser("kill", help="Emergency stop: kill active sessions and abort operations")
    p_kill.add_argument("--reset", action="store_true", help="Reset an engaged kill-switch")

    # run
    p_run = subparsers.add_parser("run", help="Execute an autonomous natural language computer task")
    p_run.add_argument("instruction", help="Natural language instruction (e.g. 'open Notepad and type Hello')")
    p_run.add_argument("--no-auto-activate", dest="auto_activate", action="store_false", default=True)
    p_run.add_argument("--max-steps", type=int, default=10)

    # launch
    p_launch = subparsers.add_parser("launch", help="Launch a Windows application")
    p_launch.add_argument("app_name", help="Application name or executable path (e.g. notepad, calc)")
    p_launch.add_argument("arguments", nargs="*", help="Optional arguments for the app")

    # windows
    subparsers.add_parser("windows", help="List visible application windows")

    # focus
    p_focus = subparsers.add_parser("focus", help="Focus a specific window")
    p_focus.add_argument("target", help="Window title substring or HWND integer")

    # click
    p_click = subparsers.add_parser("click", help="Click at desktop screen coordinates")
    p_click.add_argument("x", type=int, help="X coordinate")
    p_click.add_argument("y", type=int, help="Y coordinate")
    p_click.add_argument("--button", choices=["left", "right", "double"], default="left")

    # type
    p_type = subparsers.add_parser("type", help="Type text into the focused window")
    p_type.add_argument("text", help="Text to type")

    # screenshot
    p_ss = subparsers.add_parser("screenshot", help="Capture a desktop or window screenshot")
    p_ss.add_argument("--window", help="Optional window title substring to capture")
    p_ss.add_argument("--output", help="Optional file path to save PNG")

    # clipboard
    p_clip = subparsers.add_parser("clipboard", help="Interact with Windows clipboard")
    p_clip.add_argument("clipboard_action", choices=["get", "set"])
    p_clip.add_argument("text", nargs="?", default="", help="Text to set into clipboard")

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        return 0

    commands = {
        "status": cmd_status,
        "session": cmd_session,
        "kill": cmd_kill,
        "run": cmd_run,
        "launch": cmd_launch,
        "windows": cmd_windows,
        "focus": cmd_focus,
        "click": cmd_click,
        "type": cmd_type,
        "screenshot": cmd_screenshot,
        "clipboard": cmd_clipboard,
    }

    cmd_fn = commands.get(args.subcommand)
    if cmd_fn:
        try:
            return cmd_fn(args)
        except Exception as e:
            print(f"[ERROR] Exception during CLI execution: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
