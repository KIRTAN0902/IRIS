"""IRIS Agent Tools for Windows Computer Control and Real-Time Desktop Automation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import RiskLevel, Tool, VerificationStrategy
from app.computer.contracts import ComputerTaskRequest
from app.computer.engine import computer_engine
from app.computer.screen_perception import ScreenPerception
from app.computer.session import session_manager
from app.models.user import User


class ComputerControlParams(BaseModel):
    instruction: str = Field(
        ...,
        description=(
            "The desktop operation or task to perform on the user's Windows laptop "
            "(e.g., 'open Notepad and type Hello World', 'launch Calculator', 'focus Chrome', 'type into current window')."
        ),
    )
    verify_result: bool = Field(
        default=True,
        description="Whether to observe and verify that the target application opened or text was typed.",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=2.0,
        le=300.0,
        description="Maximum time allowed for the task execution in seconds.",
    )


class ComputerControlTool(Tool):
    name = "computer_control"
    description = (
        "Operate and control the user's Windows computer in real time. Can launch desktop applications "
        "(e.g. Notepad, Calculator, Paint, Chrome, Terminal), focus windows, type text, click buttons, "
        "manage the clipboard, and visually verify that the requested desktop state is achieved. "
        "Use this tool whenever the user asks to operate, control, or interact with their computer."
    )
    parameters_schema = ComputerControlParams
    read_only = False
    risk_level = RiskLevel.ORDINARY_WRITE
    verification_strategy = VerificationStrategy.CUSTOM

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        instruction = kwargs.get("instruction", "").strip()
        if not instruction:
            return ToolResult(tool_name=self.name, success=False, error="Instruction is required.")

        verify = kwargs.get("verify_result", True)
        timeout = float(kwargs.get("timeout_seconds", 60.0))

        req = ComputerTaskRequest(
            instruction=instruction,
            auto_activate=True,
            verify_result=verify,
            timeout_seconds=timeout,
        )

        result = computer_engine.execute_task(req)
        success = result.status == "success"

        summary_parts = [result.summary]
        if result.verified and result.verification_summary:
            summary_parts.append(f"✓ {result.verification_summary}")
        elif not success:
            summary_parts.append(f"Status: {result.status}")

        return ToolResult(
            tool_name=self.name,
            success=success,
            data=result.to_dict(),
            summary="\n".join(summary_parts),
        )


class ObserveScreenParams(BaseModel):
    window: str | None = Field(
        default=None,
        description="Optional title or substring of a window to capture, or null for the whole desktop display.",
    )


class ObserveScreenTool(Tool):
    name = "observe_screen"
    description = (
        "Observe the current state of the user's Windows desktop or a specific application window. "
        "Captures a visual screenshot to perceive what is displayed on screen."
    )
    parameters_schema = ObserveScreenParams
    read_only = True
    risk_level = RiskLevel.READ_ONLY

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        window = kwargs.get("window")
        if not session_manager.is_active:
            session_manager.activate_session(
                reason="Agent screen observation",
                expiry_minutes=5,
                authorized_by="iris_agent",
            )

        if window:
            res = ScreenPerception.capture_window_screenshot(window)
        else:
            res = ScreenPerception.capture_screenshot()

        if not res.get("success"):
            return ToolResult(tool_name=self.name, success=False, error=res.get("error", "Failed to capture screen."))

        summary = f"Desktop screenshot captured ({res.get('width')}x{res.get('height')})."
        if window:
            summary = f"Screenshot of window '{window}' captured ({res.get('width')}x{res.get('height')})."

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "width": res.get("width"),
                "height": res.get("height"),
                "mime_type": res.get("mime_type"),
                "bytes_count": res.get("bytes_count"),
            },
            summary=summary,
        )


class EmergencyStopParams(BaseModel):
    reason: str = Field(
        default="User requested emergency stop",
        description="Reason for invoking the emergency stop.",
    )


class EmergencyComputerStopTool(Tool):
    name = "emergency_computer_stop"
    description = (
        "Emergency immediate stop for computer control. Instantly aborts any active desktop actions, "
        "revokes all execution permissions, and terminates active sessions."
    )
    parameters_schema = EmergencyStopParams
    read_only = False
    risk_level = RiskLevel.SENSITIVE

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        reason = kwargs.get("reason", "Emergency stop triggered")
        session_manager.trigger_kill_switch(source="agent_tool")
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"kill_switch_engaged": True, "reason": reason},
            summary="🚨 Emergency Kill-Switch engaged. Computer control terminated immediately.",
        )


def computer_tools() -> list[Tool]:
    """Return computer control agent tools."""
    return [
        ComputerControlTool(),
        ObserveScreenTool(),
        EmergencyComputerStopTool(),
    ]
