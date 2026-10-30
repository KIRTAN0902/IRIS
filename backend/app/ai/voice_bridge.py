"""IRIS Unified Voice Bridge: Connects real-time voice channels to P1 Supervisor and P2 Device Intelligence.

Eliminates the previous restricted 9-function voice silo.
Routes all speech commands, device actions, task queries, and screen perceptions
through the shared P1/P2 capability and reasoning infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agent.supervisor import IrisSupervisor
from app.devices.android.executor import android_device_executor
from app.devices.contracts import DeviceExecutionRequest, DeviceType
from app.devices.registry import default_registry
from app.devices.target_resolver import default_target_resolver
from app.devices.windows.executor import WindowsDeviceExecutor
from app.models.user import User
from app.services.screen_perception_service import screen_perception_service

logger = logging.getLogger("iris.ai.voice_bridge")

_windows_executor = WindowsDeviceExecutor()


class UnifiedVoiceBridge:
    """Bridges Gemini Live function calls and turn-based voice to IRIS Core."""

    def __init__(
        self,
        db_factory: Callable[[], Session],
        user: User,
        client_ws: Any | None = None,
        correlation_id: str = "",
    ) -> None:
        self.db_factory = db_factory
        self.user = user
        self.client_ws = client_ws
        self.correlation_id = correlation_id or f"voice_corr_{int(time.time() * 1000)}"

    # --- Core Universal Capabilities -----------------------------------------

    async def execute_iris_command(self, command: str) -> str:
        """Execute any natural language request, complex query, or task through the unified P1 IRIS Supervisor."""
        with self.db_factory() as db:
            response, _ = await IrisSupervisor.process(
                db=db,
                user=self.user,
                user_message=command,
            )
            return response.message

    async def open_application(
        self, app_name: str, target_device: str = "", arguments: str = ""
    ) -> str:
        """Launch or open an application on the Windows laptop or Android phone, with dynamic discovery and browser fallback."""
        clean_app = app_name.strip()
        if not clean_app:
            return "Please specify the application you would like to open."

        # Dynamic Target Device Resolution via P2 Resolver
        query = f"Open {clean_app} on {target_device}" if target_device else f"Open {clean_app}"
        resolution = default_target_resolver.resolve(query, client_device=target_device or None)
        target_dev = resolution.target_device

        # Explicit target device override
        if target_device:
            low_dev = target_device.lower()
            if any(k in low_dev for k in ["phone", "mobile", "android", "realme"]):
                target_dev = DeviceType.ANDROID_PHONE
            elif any(k in low_dev for k in ["laptop", "pc", "workstation", "windows"]):
                target_dev = DeviceType.WINDOWS_LAPTOP

        # 1. Android Phone Execution via Sovereign Mesh
        if target_dev == DeviceType.ANDROID_PHONE:
            req = DeviceExecutionRequest(
                target_device_id="phone_android",
                target_device_type=DeviceType.ANDROID_PHONE,
                capability_id="android.app.launch",
                parameters={"app_name": clean_app, "package_name": None},
                correlation_id=self.correlation_id,
            )
            with self.db_factory() as db:
                res = await android_device_executor.execute_async(req, db=db, user_id=str(self.user.id))
                if res.success:
                    # Also notify client websocket if direct
                    if self.client_ws:
                        try:
                            await self.client_ws.send_json({"type": "launch_mobile_app", "app": clean_app})
                        except Exception:
                            pass
                    return f"Opening {clean_app.title()} on your Android phone."
                return f"I couldn't open {clean_app} on your phone: {res.error}"

        # 2. Windows Laptop Execution via Dynamic Windows Engine
        with self.db_factory() as db:
            from app.services import mesh_relay_service as mrs
            if not mrs.is_local_windows_host():
                if not default_registry.is_device_online(DeviceType.WINDOWS_LAPTOP, db=db, user_id=str(self.user.id)):
                    return "Your Windows laptop is currently offline or unreachable on the Sovereign Mesh."

            req = DeviceExecutionRequest(
                target_device_id="laptop_windows",
                target_device_type=DeviceType.WINDOWS_LAPTOP,
                capability_id="windows.app.launch",
                parameters={"app_name": clean_app, "argument": arguments},
                correlation_id=self.correlation_id,
            )
            res = _windows_executor.execute(req)
            if res.success:
                data = res.data or {}
                if "browser" in data:
                    return f"Opened {clean_app.title()} in {data.get('browser')} at {data.get('url')} on your Windows laptop."
                return f"Opened {data.get('app_name', clean_app.title())} on your Windows laptop."
            return f"Could not open {clean_app} on your laptop: {res.error}"

    async def get_battery_status(self, target_device: str = "") -> str:
        """Check the live battery percentage, charging state, and power telemetry of the laptop or phone."""
        with self.db_factory() as db:
            low = target_device.lower()
            lines = []

            # Check Laptop Battery
            if not target_device or any(k in low for k in ["laptop", "pc", "windows", "workstation"]):
                req_win = DeviceExecutionRequest(
                    target_device_id="laptop_windows",
                    target_device_type=DeviceType.WINDOWS_LAPTOP,
                    capability_id="windows.system.battery",
                )
                res_win = _windows_executor.execute(req_win)
                if res_win.success and res_win.data:
                    pct = res_win.data.get("battery_level_percent")
                    chg = res_win.data.get("is_charging")
                    state = "charging" if chg else "on battery"
                    lines.append(f"Laptop battery is at {pct}% ({state})." if pct is not None else "Laptop is plugged into AC power.")

            # Check Phone Battery
            if not target_device or any(k in low for k in ["phone", "mobile", "android"]):
                req_phone = DeviceExecutionRequest(
                    target_device_id="phone_android",
                    target_device_type=DeviceType.ANDROID_PHONE,
                    capability_id="android.system.battery",
                )
                res_phone = await android_device_executor.execute_async(req_phone, db=db, user_id=str(self.user.id))
                if res_phone.success and res_phone.data:
                    pct = res_phone.data.get("battery_level")
                    chg = res_phone.data.get("is_charging")
                    state = "charging" if chg else "on battery"
                    lines.append(f"Phone battery is at {pct}% ({state})." if pct is not None else "Phone battery status is available.")

            return " ".join(lines) if lines else "Battery telemetry could not be retrieved."

    async def lock_workstation(self) -> str:
        """Immediately lock the Windows laptop workstation display for security and privacy."""
        req = DeviceExecutionRequest(
            target_device_id="laptop_windows",
            target_device_type=DeviceType.WINDOWS_LAPTOP,
            capability_id="windows.system.lock",
        )
        res = _windows_executor.execute(req)
        return "Windows workstation locked." if res.success else f"Could not lock workstation: {res.error}"

    async def manage_daily_tasks(
        self,
        action: str,
        title: str = "",
        task_id: int = 0,
        priority: str = "MEDIUM",
        estimated_minutes: int = 30,
    ) -> str:
        """Create, inspect, or complete tasks in IRIS core (action: 'create', 'list', 'complete')."""
        with self.db_factory() as db:
            act = action.lower().strip()
            if act == "create":
                if not title:
                    return "Task title is required to create a task."
                from app.models.enums import LifeArea, TaskPriority
                from app.schemas.task import TaskCreate
                from app.services import task_service

                t_in = TaskCreate(
                    title=title,
                    area=LifeArea.PERSONAL,
                    priority=getattr(TaskPriority, priority.upper(), TaskPriority.MEDIUM),
                    estimated_duration=estimated_minutes,
                )
                t = task_service.create_task(db, self.user.id, t_in)
                return f"Created task #{t.id}: '{t.title}' with {t.priority.title()} priority."

            elif act in ("list", "get", "today"):
                from app.models.enums import TaskStatus
                from app.models.task import Task

                open_tasks = (
                    db.query(Task)
                    .filter(Task.user_id == self.user.id, Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]))
                    .order_by(Task.deadline.asc().nullslast(), Task.priority.desc())
                    .all()
                )
                if not open_tasks:
                    return "You have no open tasks scheduled for today."
                task_items = [f"{t.title} ({t.priority.title()} priority)" for t in open_tasks[:5]]
                return f"You have {len(open_tasks)} open task(s): " + "; ".join(task_items) + "."

            elif act in ("complete", "done", "finish"):
                from app.models.task import Task
                from app.services import task_service

                t = None
                if task_id:
                    t = db.query(Task).filter(Task.user_id == self.user.id, Task.id == task_id).first()
                elif title:
                    t = db.query(Task).filter(Task.user_id == self.user.id, Task.title.ilike(f"%{title}%")).first()
                if not t:
                    return f"Could not find a task matching '{title or task_id}'."
                task_service.complete_task(db, self.user.id, t.id, None)
                return f"Marked task #{t.id} '{t.title}' as completed."

            return f"Unrecognized task action '{action}'."

    async def inspect_current_screen(
        self, target_device: str = "", question: str = ""
    ) -> str:
        """Capture and inspect what is currently visible on the user's laptop or phone screen to answer visual questions."""
        with self.db_factory() as db:
            success, message, vision_res = await screen_perception_service.capture_and_analyze(
                db=db,
                user=self.user,
                target_device_hint=target_device,
                question=question,
                client_ws=self.client_ws,
                timeout_seconds=15.0,
            )
            if success and vision_res:
                return f"Screen observation: {vision_res.summary}"
            return message

    async def query_screen_followup(self, question: str) -> str:
        """Answer follow-up questions referencing the screen (e.g. 'Which button should I click?')."""
        with self.db_factory() as db:
            return await screen_perception_service.answer_visual_followup(
                question=question,
                db=db,
                user=self.user,
                client_ws=self.client_ws,
            )

    # --- Backwards Compatibility Wrappers for Gemini Live -------------------

    async def launch_laptop_app(self, app_name: str, directory: str = "") -> str:
        return await self.open_application(app_name=app_name, target_device="laptop", arguments=directory)

    async def launch_mobile_app(self, app_name: str) -> str:
        return await self.open_application(app_name=app_name, target_device="phone")

    async def execute_terminal_command(self, command: str) -> str:
        return await self.execute_iris_command(f"run command {command}")

    async def get_laptop_status(self) -> str:
        return await self.get_battery_status("laptop")

    async def lock_laptop(self) -> str:
        return await self.lock_workstation()

    async def create_daily_task(
        self, title: str, area: str = "PERSONAL", priority: str = "MEDIUM", estimated_minutes: int = 30
    ) -> str:
        return await self.manage_daily_tasks("create", title=title, priority=priority, estimated_minutes=estimated_minutes)

    async def get_today_tasks(self) -> str:
        return await self.manage_daily_tasks("list")

    async def complete_task(self, task_title_or_id: str) -> str:
        task_id = int(task_title_or_id) if task_title_or_id.isdigit() else 0
        return await self.manage_daily_tasks("complete", title=task_title_or_id, task_id=task_id)

    # --- Tool Registration for LiveConnectConfig -----------------------------

    def get_callable_tools(self) -> list[Callable[..., Any]]:
        """Returns the list of typed functions to pass into Google GenAI LiveConnectConfig."""
        return [
            self.execute_iris_command,
            self.open_application,
            self.get_battery_status,
            self.lock_workstation,
            self.manage_daily_tasks,
            self.inspect_current_screen,
            self.query_screen_followup,
            # Legacy function definitions for models configured with legacy tools
            self.launch_laptop_app,
            self.launch_mobile_app,
            self.execute_terminal_command,
            self.get_laptop_status,
            self.lock_laptop,
            self.create_daily_task,
            self.get_today_tasks,
            self.complete_task,
        ]

    async def dispatch_tool_call(self, name: str, args: dict[str, Any]) -> str:
        """Dispatches an intercepted tool call by name to the unified capability method."""
        tool_map = {
            "execute_iris_command": self.execute_iris_command,
            "open_application": self.open_application,
            "get_battery_status": self.get_battery_status,
            "lock_workstation": self.lock_workstation,
            "manage_daily_tasks": self.manage_daily_tasks,
            "inspect_current_screen": self.inspect_current_screen,
            "query_screen_followup": self.query_screen_followup,
            # Legacy aliases
            "launch_laptop_app": self.launch_laptop_app,
            "launch_mobile_app": self.launch_mobile_app,
            "execute_terminal_command": self.execute_terminal_command,
            "get_laptop_status": self.get_laptop_status,
            "lock_laptop": self.lock_laptop,
            "create_daily_task": self.create_daily_task,
            "get_today_tasks": self.get_today_tasks,
            "complete_task": self.complete_task,
        }
        fn = tool_map.get(name)
        if not fn:
            logger.warning("Voice tool '%s' not recognized; falling back to unified supervisor", name)
            return await self.execute_iris_command(f"{name} {args}")

        try:
            return await fn(**args)
        except Exception as exc:
            logger.exception("Error executing voice tool %s: %s", name, exc)
            return f"Error executing {name}: {exc}"
