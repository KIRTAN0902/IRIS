"""IRIS Computer Control subsystem: Desktop automation, screen perception, and session management."""

from app.computer.contracts import (
    ActionResult,
    ActionRiskLevel,
    ComputerAction,
    ComputerActionType,
    ComputerTaskRequest,
    ComputerTaskResult,
    SessionInfo,
    SessionState,
)
from app.computer.engine import ComputerControlEngine, computer_engine
from app.computer.gui_ops import GuiOps
from app.computer.native_ops import NativeOps
from app.computer.screen_perception import ScreenPerception
from app.computer.security import ComputerSecurityPolicy, security_policy
from app.computer.session import (
    ComputerSessionManager,
    KillSwitchTriggeredError,
    SessionSecurityError,
    session_manager,
)

__all__ = [
    "ActionResult",
    "ActionRiskLevel",
    "ComputerAction",
    "ComputerActionType",
    "ComputerControlEngine",
    "ComputerSecurityPolicy",
    "ComputerSessionManager",
    "ComputerTaskRequest",
    "ComputerTaskResult",
    "GuiOps",
    "KillSwitchTriggeredError",
    "NativeOps",
    "ScreenPerception",
    "SessionInfo",
    "SessionSecurityError",
    "SessionState",
    "computer_engine",
    "security_policy",
    "session_manager",
]
