"""Data contracts and schemas for IRIS Computer Control."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class SessionState(str, Enum):
    """Computer control session lifecycle states."""

    BACKGROUND = "background"    # Companion online, desktop access strictly disabled
    ACTIVE = "active"            # Authorized session active, actions permitted
    PAUSED = "paused"            # Temporarily paused, in-flight stopped, no new actions
    TERMINATED = "terminated"    # Revoked/stopped, temporary credentials cleared


class ActionRiskLevel(str, Enum):
    """Risk classification for desktop actions."""

    ORDINARY = "ordinary"          # Safe routine operations (typing, clicking, opening apps)
    SENSITIVE = "sensitive"        # Financial, messaging, bulk modifications, elevated cmds
    DESTRUCTIVE = "destructive"    # System file deletions, format, security disable (blocked)


class ComputerActionType(str, Enum):
    """Supported computer control action primitives."""

    # Screen & Perception
    OBSERVE_SCREEN = "computer.observe"
    INSPECT_WINDOW = "computer.window.inspect"

    # Shell & Native
    SHELL_EXECUTE = "computer.shell"
    PROCESS_LIST = "computer.process.list"
    PROCESS_INSPECT = "computer.process.inspect"
    PROCESS_KILL = "computer.process.kill"

    # Application & Window
    APP_LAUNCH = "computer.open_application"
    WINDOW_LIST = "computer.window.list"
    WINDOW_FOCUS = "computer.window.focus"
    WINDOW_MINIMIZE = "computer.window.minimize"
    WINDOW_MAXIMIZE = "computer.window.maximize"
    WINDOW_CLOSE = "computer.window.close"

    # Filesystem
    FILE_LIST = "computer.files.list"
    FILE_READ = "computer.files.read"
    FILE_CREATE = "computer.files.create"
    FILE_MOVE = "computer.files.move"
    FILE_RENAME = "computer.files.rename"
    FILE_DELETE = "computer.files.delete"

    # Mouse Control
    MOUSE_CLICK = "computer.click"
    MOUSE_DOUBLE_CLICK = "computer.double_click"
    MOUSE_RIGHT_CLICK = "computer.right_click"
    MOUSE_MOVE = "computer.move_mouse"
    MOUSE_DRAG = "computer.drag"
    MOUSE_SCROLL = "computer.scroll"

    # Keyboard Control
    KEYBOARD_TYPE = "computer.type"
    KEYBOARD_PRESS = "computer.keypress"
    KEYBOARD_HOTKEY = "computer.hotkey"

    # Clipboard Control
    CLIPBOARD_READ = "computer.clipboard.read"
    CLIPBOARD_WRITE = "computer.clipboard.write"
    CLIPBOARD_PASTE = "computer.clipboard.paste"

    # Utility
    WAIT = "computer.wait"

    # Session Control
    SESSION_STATUS = "computer.session.status"
    SESSION_PAUSE = "computer.session.pause"
    SESSION_RESUME = "computer.session.resume"
    SESSION_STOP = "computer.session.stop"


class ComputerAction(BaseModel):
    """Specification of a single action to execute on the computer."""

    action_type: ComputerActionType
    params: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    risk_level: ActionRiskLevel = ActionRiskLevel.ORDINARY
    approval_token: str | None = None


class ActionResult(BaseModel):
    """Outcome of an individual computer action."""

    action_type: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    verified: bool = False
    verification_details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ComputerTaskRequest(BaseModel):
    """High-level task request to control the computer."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:10]}")
    instruction: str = Field(..., description="Natural language goal or task to perform on the laptop")
    actions: list[ComputerAction] | None = Field(default=None, description="Optional explicit sequence of actions")
    auto_activate: bool = Field(default=True, description="Whether to activate a computer-control session if idle")
    timeout_seconds: float = Field(default=60.0, ge=2.0, le=300.0)
    verify_result: bool = Field(default=True, description="Whether to observe and verify the resulting state")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ComputerTaskResult(BaseModel):
    """Consolidated outcome of a computer control execution task."""

    task_id: str
    session_id: str | None
    status: str  # "success" | "partial" | "failed" | "cancelled" | "approval_required"
    summary: str
    steps: list[ActionResult] = Field(default_factory=list)
    verified: bool = False
    verification_summary: str | None = None
    duration_ms: int = 0
    artifacts: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class SessionInfo(BaseModel):
    """Telemetry and state for a computer-control session."""

    session_id: str
    state: SessionState
    created_at: datetime
    expires_at: datetime
    last_activity_at: datetime
    reason: str
    is_interactive_desktop: bool
    kill_switch_engaged: bool = False
    kill_switch_source: str | None = None
    session_token: str | None = None
    actions_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
