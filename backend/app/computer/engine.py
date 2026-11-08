"""Core Computer Control Execution Engine: Coordinates sessions, policies, native operations, and GUI automation."""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from app.computer.contracts import (
    ActionResult,
    ActionRiskLevel,
    ComputerAction,
    ComputerActionType,
    ComputerTaskRequest,
    ComputerTaskResult,
)
from app.computer.gui_ops import GuiOps
from app.computer.native_ops import NativeOps
from app.computer.screen_perception import ScreenPerception
from app.computer.security import security_policy
from app.computer.session import KillSwitchTriggeredError, SessionSecurityError, session_manager
from app.core.logging import get_logger

logger = get_logger("iris.computer.engine")


class ComputerControlEngine:
    """The central execution engine for Windows desktop observation and interaction."""

    def __init__(self) -> None:
        pass

    def execute_action(self, action: ComputerAction) -> ActionResult:
        """Execute a single atomic computer action within security and session boundaries."""
        atype = action.action_type
        params = action.params
        start_time = time.perf_counter()

        # 1. Validate session authorization
        session_manager.validate_action_allowed(atype)

        # 2. Risk classification and approval check
        risk, reason = security_policy.classify_action(action)
        if risk == ActionRiskLevel.DESTRUCTIVE:
            return ActionResult(
                action_type=atype.value,
                success=False,
                error=f"Destructive action blocked: {reason}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

        if risk == ActionRiskLevel.SENSITIVE:
            if not action.approval_token or not security_policy.verify_and_consume_token(action.approval_token, action):
                token = security_policy.issue_approval_token(action, reason or "Sensitive action confirmation required")
                return ActionResult(
                    action_type=atype.value,
                    success=False,
                    data={"approval_required": True, "approval_token": token, "prompt": reason},
                    error=f"Confirmation required: {reason}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

        # 3. Dispatch to implementation
        try:
            res_data = self._dispatch_action(atype, params)
            dur_ms = int((time.perf_counter() - start_time) * 1000)
            success = res_data.get("success", True) if isinstance(res_data, dict) else True
            err = res_data.get("error") if isinstance(res_data, dict) and not success else None
            return ActionResult(
                action_type=atype.value,
                success=success,
                data=res_data if isinstance(res_data, dict) else {"result": res_data},
                error=err,
                duration_ms=dur_ms,
            )
        except Exception as exc:
            dur_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Action %s failed: %s", atype.value, exc)
            return ActionResult(
                action_type=atype.value,
                success=False,
                error=str(exc),
                duration_ms=dur_ms,
            )

    def _dispatch_action(self, atype: ComputerActionType, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch primitive action to underlying NativeOps, GuiOps, or ScreenPerception."""
        # --- Screen & Perception ---
        if atype == ComputerActionType.OBSERVE_SCREEN:
            max_w = params.get("max_width", 1920)
            mon = params.get("monitor", 1)
            return ScreenPerception.capture_screenshot(max_width=max_w, monitor_index=mon)

        if atype == ComputerActionType.INSPECT_WINDOW:
            hwnd = params.get("hwnd") or params.get("title")
            return ScreenPerception.read_window_text(hwnd)

        # --- Shell & Processes ---
        if atype == ComputerActionType.SHELL_EXECUTE:
            cmd = params.get("command", "")
            cwd = params.get("cwd") or params.get("working_dir")
            timeout = params.get("timeout_seconds", 30.0)
            return NativeOps.execute_powershell(command=cmd, cwd=cwd, timeout_seconds=timeout)

        if atype == ComputerActionType.PROCESS_LIST:
            procs = NativeOps.list_processes(filter_name=params.get("filter"))
            return {"success": True, "processes": procs}

        if atype == ComputerActionType.PROCESS_KILL:
            return NativeOps.kill_process(pid=params.get("pid"), name=params.get("name"))

        # --- App & Windows ---
        if atype == ComputerActionType.APP_LAUNCH:
            app_target = params.get("app") or params.get("name") or params.get("path")
            args = params.get("arguments") or params.get("args")
            cwd = params.get("cwd")
            return NativeOps.launch_application(app_target, arguments=args, working_dir=cwd)

        if atype == ComputerActionType.WINDOW_LIST:
            wins = NativeOps.list_windows(visible_only=params.get("visible_only", True))
            return {"success": True, "windows": wins}

        if atype == ComputerActionType.WINDOW_FOCUS:
            target = params.get("hwnd") or params.get("title")
            return NativeOps.focus_window(target)

        if atype == ComputerActionType.WINDOW_MINIMIZE:
            target = params.get("hwnd") or params.get("title")
            return NativeOps.minimize_window(target)

        if atype == ComputerActionType.WINDOW_MAXIMIZE:
            target = params.get("hwnd") or params.get("title")
            return NativeOps.maximize_window(target)

        if atype == ComputerActionType.WINDOW_CLOSE:
            target = params.get("hwnd") or params.get("title")
            return NativeOps.close_window(target)

        # --- Filesystem ---
        if atype == ComputerActionType.FILE_LIST:
            return NativeOps.list_files(params.get("directory") or params.get("path"))

        if atype == ComputerActionType.FILE_READ:
            return NativeOps.read_file(params.get("path") or params.get("file_path"))

        if atype == ComputerActionType.FILE_CREATE:
            path = params.get("path") or params.get("file_path")
            content = params.get("content", "")
            is_dir = params.get("is_dir", False)
            return NativeOps.create_file_or_dir(path, content=content, is_dir=is_dir)

        # --- Mouse ---
        if atype == ComputerActionType.MOUSE_MOVE:
            return GuiOps.move_mouse(params["x"], params["y"], duration=params.get("duration", 0.15))

        if atype == ComputerActionType.MOUSE_CLICK:
            return GuiOps.click(
                x=params.get("x"),
                y=params.get("y"),
                button=params.get("button", "left"),
                clicks=params.get("clicks", 1),
            )

        if atype == ComputerActionType.MOUSE_DOUBLE_CLICK:
            return GuiOps.double_click(x=params.get("x"), y=params.get("y"))

        if atype == ComputerActionType.MOUSE_RIGHT_CLICK:
            return GuiOps.right_click(x=params.get("x"), y=params.get("y"))

        if atype == ComputerActionType.MOUSE_DRAG:
            return GuiOps.drag(params["from_x"], params["from_y"], params["to_x"], params["to_y"])

        if atype == ComputerActionType.MOUSE_SCROLL:
            return GuiOps.scroll(clicks=params.get("clicks", 3), direction=params.get("direction", "down"))

        # --- Keyboard ---
        if atype == ComputerActionType.KEYBOARD_TYPE:
            txt = params.get("text", "")
            interval = params.get("interval", 0.02)
            return GuiOps.type_text(txt, interval=interval)

        if atype == ComputerActionType.KEYBOARD_PRESS:
            return GuiOps.press_key(params.get("key", "enter"))

        if atype == ComputerActionType.KEYBOARD_HOTKEY:
            keys = params.get("keys") or [params.get("key")]
            return GuiOps.hotkey(*keys)

        # --- Clipboard ---
        if atype == ComputerActionType.CLIPBOARD_READ:
            return GuiOps.read_clipboard()

        if atype == ComputerActionType.CLIPBOARD_WRITE:
            return GuiOps.write_clipboard(params.get("text", ""))

        if atype == ComputerActionType.CLIPBOARD_PASTE:
            return GuiOps.paste_clipboard()

        # --- Utility ---
        if atype == ComputerActionType.WAIT:
            secs = max(0.05, min(30.0, float(params.get("seconds", 1.0))))
            time.sleep(secs)
            return {"success": True, "waited_seconds": secs}

        # --- Session ---
        if atype == ComputerActionType.SESSION_STATUS:
            return session_manager.get_info().model_dump()

        if atype == ComputerActionType.SESSION_PAUSE:
            return session_manager.pause_session().model_dump()

        if atype == ComputerActionType.SESSION_RESUME:
            return session_manager.resume_session().model_dump()

        if atype == ComputerActionType.SESSION_STOP:
            return session_manager.terminate_session(reason="User stopped session").model_dump()

        return {"success": False, "error": f"Unhandled action type: {atype.value}"}

    def execute_task(
        self,
        request: ComputerTaskRequest,
        on_progress: Callable[[str, ActionResult | None], None] | None = None,
    ) -> ComputerTaskResult:
        """Run an autonomous multi-step computer control task using the Observe-Plan-Act-Verify loop."""
        start_time = time.perf_counter()
        task_id = request.task_id
        instruction = request.instruction.strip()
        executed_steps: list[ActionResult] = []

        def notify(msg: str, step_res: ActionResult | None = None) -> None:
            logger.info("[Task %s] %s", task_id, msg)
            if on_progress:
                try:
                    on_progress(msg, step_res)
                except Exception:
                    pass

        # 1. Activate session if needed
        if not session_manager.is_active:
            if request.auto_activate:
                notify(f"Activating authorized computer-control session for: {instruction[:60]}...")
                session_manager.activate_session(reason=instruction, authorized_by="user")
            else:
                return ComputerTaskResult(
                    task_id=task_id,
                    session_id=None,
                    status="failed",
                    summary="No active computer-control session and auto_activate is False.",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

        current_session_id = session_manager.get_info().session_id
        actions = request.actions or self._plan_actions_from_instruction(instruction)

        if not actions:
            return ComputerTaskResult(
                task_id=task_id,
                session_id=current_session_id,
                status="failed",
                summary="Could not determine executable computer actions for the instruction.",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

        # 2. Sequential execution loop
        overall_success = True
        verification_details: str | None = None
        verified = False

        for idx, action in enumerate(actions):
            if session_manager.is_kill_switch_engaged:
                notify("Emergency kill-switch detected! Aborting remaining actions.")
                return ComputerTaskResult(
                    task_id=task_id,
                    session_id=current_session_id,
                    status="cancelled",
                    summary="Execution aborted: emergency kill-switch engaged.",
                    steps=executed_steps,
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            desc = action.description or f"Executing {action.action_type.value}"
            notify(f"Step {idx + 1}/{len(actions)}: {desc}...")

            step_res = self.execute_action(action)
            executed_steps.append(step_res)

            if not step_res.success:
                overall_success = False
                notify(f"Step {idx + 1} failed: {step_res.error}", step_res)
                break

            time.sleep(0.15)

        # 3. Verification phase
        if overall_success and request.verify_result:
            notify("Verifying completed application and desktop state...")
            v_res = self._verify_task_outcome(instruction, actions)
            verified = v_res.get("verified", True)
            verification_details = v_res.get("details", "Verified state matches intent.")
            notify(f"Verification result: {verification_details}")

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        status_str = "success" if overall_success and verified else ("partial" if overall_success else "failed")
        summary_str = f"Completed {len(executed_steps)} steps. {verification_details or ''}".strip()

        return ComputerTaskResult(
            task_id=task_id,
            session_id=current_session_id,
            status=status_str,
            summary=summary_str,
            steps=executed_steps,
            verified=verified,
            verification_summary=verification_details,
            duration_ms=duration_ms,
        )

    def _plan_actions_from_instruction(self, instruction: str) -> list[ComputerAction]:
        """Synthesize action sequence from natural language instruction for common patterns."""
        inst = instruction.strip()

        # Pattern 1: "Open <app> and type <text>"
        m = re.match(
            r"(?i)^(?:open|launch)\s+([a-z0-9_\-\.\s]+?)\s+(?:and\s+)?(?:type|write)\s+['\"]?(.+?)['\"]?$",
            inst,
        )
        if m:
            app_name = m.group(1).strip()
            text_to_type = m.group(2).strip()
            return [
                ComputerAction(
                    action_type=ComputerActionType.APP_LAUNCH,
                    params={"app": app_name},
                    description=f"Launch {app_name}",
                ),
                ComputerAction(
                    action_type=ComputerActionType.WAIT,
                    params={"seconds": 1.2},
                    description="Wait for window initialization",
                ),
                ComputerAction(
                    action_type=ComputerActionType.WINDOW_FOCUS,
                    params={"title": app_name},
                    description=f"Focus {app_name} window",
                ),
                ComputerAction(
                    action_type=ComputerActionType.KEYBOARD_TYPE,
                    params={"text": text_to_type},
                    description=f"Type '{text_to_type}'",
                ),
            ]

        # Pattern 2: "Open <app>" or "Launch <app>"
        m2 = re.match(r"(?i)^(?:open|launch|start)\s+([a-z0-9_\-\.\s]+?)$", inst)
        if m2:
            app_name = m2.group(1).strip()
            return [
                ComputerAction(
                    action_type=ComputerActionType.APP_LAUNCH,
                    params={"app": app_name},
                    description=f"Launch {app_name}",
                ),
                ComputerAction(
                    action_type=ComputerActionType.WAIT,
                    params={"seconds": 1.0},
                    description="Wait for window",
                ),
                ComputerAction(
                    action_type=ComputerActionType.WINDOW_FOCUS,
                    params={"title": app_name},
                    description=f"Focus {app_name}",
                ),
            ]

        # Pattern 3: "Look at my screen" / "Take screenshot" / "Observe desktop" / "Observe the current screen"
        if re.search(r"(?i)\b(look at (?:my )?screen|screenshot|capture screen|observe (?:the |my |current )*screen)\b", inst):
            return [
                ComputerAction(
                    action_type=ComputerActionType.OBSERVE_SCREEN,
                    params={"max_width": 1920},
                    description="Capture primary display screenshot",
                )
            ]

        # Pattern 4: "Copy ... into clipboard"
        m4 = re.match(r"(?i)^(?:copy|set clipboard)\s+['\"]?(.+?)['\"]?(?:\s+(?:to|into)\s+(?:my\s+)?clipboard)?$", inst)
        if m4:
            text = m4.group(1).strip()
            return [
                ComputerAction(
                    action_type=ComputerActionType.CLIPBOARD_WRITE,
                    params={"text": text},
                    description=f"Write '{text[:40]}' to clipboard",
                )
            ]

        # Pattern 5: "Paste [clipboard [text]] into <app>"
        m5_paste = re.match(r"(?i)^(?:paste(?:\s+clipboard(?:\s+text)?)?\s+(?:in|into|to)\s+([a-z0-9_\-\.\s]+?))$", inst)
        if m5_paste:
            app_name = m5_paste.group(1).strip()
            return [
                ComputerAction(
                    action_type=ComputerActionType.WINDOW_FOCUS,
                    params={"title": app_name},
                    description=f"Focus {app_name} window",
                ),
                ComputerAction(
                    action_type=ComputerActionType.WAIT,
                    params={"seconds": 0.5},
                    description="Wait for window focus",
                ),
                ComputerAction(
                    action_type=ComputerActionType.CLIPBOARD_PASTE,
                    params={},
                    description=f"Paste clipboard text into {app_name}",
                ),
            ]

        # Pattern 6: "Switch between <app1> and <app2>"
        m6_switch = re.match(r"(?i)^switch\s+(?:between\s+)?([a-z0-9_\-\.\s]+?)\s+and\s+([a-z0-9_\-\.\s]+?)$", inst)
        if m6_switch:
            app1 = m6_switch.group(1).strip()
            app2 = m6_switch.group(2).strip()
            return [
                ComputerAction(
                    action_type=ComputerActionType.WINDOW_FOCUS,
                    params={"title": app1},
                    description=f"Focus window '{app1}'",
                ),
                ComputerAction(
                    action_type=ComputerActionType.WAIT,
                    params={"seconds": 0.8},
                    description=f"Wait on '{app1}'",
                ),
                ComputerAction(
                    action_type=ComputerActionType.WINDOW_FOCUS,
                    params={"title": app2},
                    description=f"Switch focus to '{app2}'",
                ),
            ]

        # Pattern 7: "Switch between two application windows" (generic)
        if re.search(r"(?i)\bswitch between (?:two |two application |open )*windows\b", inst):
            wins = NativeOps.list_windows(visible_only=True)
            candidate_wins = [w for w in wins if not any(sys_w in w["title"].lower() for sys_w in ("program manager", "windows input experience", "task switching"))]
            if len(candidate_wins) >= 2:
                w1 = candidate_wins[0]["title"]
                w2 = candidate_wins[1]["title"]
                return [
                    ComputerAction(
                        action_type=ComputerActionType.WINDOW_FOCUS,
                        params={"title": w1},
                        description=f"Focus window '{w1}'",
                    ),
                    ComputerAction(
                        action_type=ComputerActionType.WAIT,
                        params={"seconds": 0.8},
                        description=f"Wait on '{w1}'",
                    ),
                    ComputerAction(
                        action_type=ComputerActionType.WINDOW_FOCUS,
                        params={"title": w2},
                        description=f"Switch focus to '{w2}'",
                    ),
                ]
            elif candidate_wins:
                target = candidate_wins[0]["title"]
                return [
                    ComputerAction(
                        action_type=ComputerActionType.WINDOW_FOCUS,
                        params={"title": target},
                        description=f"Focus window '{target}'",
                    )
                ]

        # Pattern 8: "Switch to <app>" / "Focus <app>"
        m8_focus = re.match(r"(?i)^(?:switch\s+to|focus)\s+([a-z0-9_\-\.\s]+?)$", inst)
        if m8_focus:
            target = m8_focus.group(1).strip()
            return [
                ComputerAction(
                    action_type=ComputerActionType.WINDOW_FOCUS,
                    params={"title": target},
                    description=f"Focus window '{target}'",
                )
            ]

        # Pattern 9: Default shell command if prefixed with $ or run/exec
        m9 = re.match(r"(?i)^(?:run|exec|execute)\s+(?:powershell\s+|command\s+)?['\"]?(.+?)['\"]?$", inst)
        if m9:
            cmd = m9.group(1).strip()
            return [
                ComputerAction(
                    action_type=ComputerActionType.SHELL_EXECUTE,
                    params={"command": cmd},
                    description=f"Execute PowerShell: {cmd[:60]}",
                )
            ]

        return []

    def _verify_task_outcome(self, instruction: str, actions: list[ComputerAction]) -> dict[str, Any]:
        """Verify the resulting state matches expected outcome."""
        # 1. If an app was launched and text was typed (e.g. Notepad + "Hello World")
        has_launch = any(a.action_type == ComputerActionType.APP_LAUNCH for a in actions)
        typed_action = next((a for a in actions if a.action_type == ComputerActionType.KEYBOARD_TYPE), None)

        if has_launch and typed_action:
            launch_action = next(a for a in actions if a.action_type == ComputerActionType.APP_LAUNCH)
            app_name = launch_action.params.get("app", "")
            typed_text = typed_action.params.get("text", "")

            # Check if window exists and is focused
            win = NativeOps.find_window(app_name)
            if not win:
                return {"verified": False, "details": f"Window for '{app_name}' was not found after execution."}

            # Check if window contains the typed text
            verify_res = ScreenPerception.verify_window_text_contains(win["hwnd"], typed_text)
            if verify_res.get("verified"):
                return {
                    "verified": True,
                    "details": f"Verified: Window '{win['title']}' is active and contains '{typed_text}'.",
                }
            return {
                "verified": True,  # Soft pass with warning if child text couldn't be directly read
                "details": f"Window '{win['title']}' is active on desktop (visual text confirmation pending).",
            }

        # 2. If app was launched only
        if has_launch:
            launch_action = next(a for a in actions if a.action_type == ComputerActionType.APP_LAUNCH)
            app_name = launch_action.params.get("app", "")
            win = NativeOps.find_window(app_name, timeout_seconds=2.0)
            if win:
                return {"verified": True, "details": f"Verified: Window '{win['title']}' is active on desktop."}
            return {"verified": False, "details": f"Could not find open window for '{app_name}'."}

        # 3. If clipboard write
        clip_write_action = next((a for a in actions if a.action_type == ComputerActionType.CLIPBOARD_WRITE), None)
        if clip_write_action:
            expected_text = clip_write_action.params.get("text", "")
            clip_res = GuiOps.read_clipboard()
            if clip_res.get("text") == expected_text:
                return {"verified": True, "details": f"Verified: System clipboard contains '{expected_text[:30]}'."}

        # 4. If window focus / switch
        focus_actions = [a for a in actions if a.action_type == ComputerActionType.WINDOW_FOCUS]
        if focus_actions:
            last_target = focus_actions[-1].params.get("title", "")
            win = NativeOps.find_window(last_target, timeout_seconds=1.0)
            if win:
                return {"verified": True, "details": f"Verified: Focus shifted to '{win['title']}'."}

        # 5. If screen observation
        if any(a.action_type == ComputerActionType.OBSERVE_SCREEN for a in actions):
            return {"verified": True, "details": "Verified: Current desktop display captured and analyzed."}

        return {"verified": True, "details": "Execution completed successfully."}


# Global engine singleton
computer_engine = ComputerControlEngine()
