"""Automated test suite for IRIS Windows Computer Control subsystem."""

import os
import time
import pytest

from app.computer.contracts import (
    ActionRiskLevel,
    ComputerAction,
    ComputerActionType,
    ComputerTaskRequest,
    SessionState,
)
from app.computer.engine import computer_engine
from app.computer.gui_ops import GuiOps
from app.computer.native_ops import NativeOps
from app.computer.screen_perception import ScreenPerception
from app.computer.security import security_policy
from app.computer.session import (
    KillSwitchTriggeredError,
    SessionSecurityError,
    session_manager,
)


def test_session_lifecycle():
    """Test session activation, pause, resume, termination, and background gating."""
    session_manager.reset_kill_switch()
    assert session_manager.get_info().state == SessionState.BACKGROUND

    # 1. Action without active session must raise SessionSecurityError
    with pytest.raises(SessionSecurityError):
        session_manager.validate_action_allowed(ComputerActionType.KEYBOARD_TYPE)

    # 2. Activate session
    session = session_manager.activate_session("pytest test session", expiry_minutes=2)
    assert session.state == SessionState.ACTIVE
    assert session_manager.is_active is True

    # 3. Action allowed when active
    session_manager.validate_action_allowed(ComputerActionType.KEYBOARD_TYPE)

    # 4. Pause session
    paused = session_manager.pause_session("Testing pause")
    assert paused.state == SessionState.PAUSED
    with pytest.raises(SessionSecurityError):
        session_manager.validate_action_allowed(ComputerActionType.KEYBOARD_TYPE)

    # 5. Resume session
    resumed = session_manager.resume_session()
    assert resumed.state == SessionState.ACTIVE

    # 6. Terminate session
    term = session_manager.terminate_session("Finished test")
    assert term.state == SessionState.BACKGROUND
    assert session_manager.is_active is False


def test_kill_switch_behavior():
    """Test emergency kill switch: immediate termination and block on further actions."""
    session_manager.reset_kill_switch()
    session_manager.activate_session("kill switch test")

    # Engage kill switch
    session_manager.trigger_kill_switch("pytest_kill_test")
    info = session_manager.get_info()
    assert info.kill_switch_engaged is True
    assert session_manager.is_active is False

    # Actions blocked
    with pytest.raises(KillSwitchTriggeredError):
        session_manager.validate_action_allowed(ComputerActionType.KEYBOARD_TYPE)

    # Activation blocked while kill switch engaged
    with pytest.raises(KillSwitchTriggeredError):
        session_manager.activate_session("should fail")

    # Reset
    reset_info = session_manager.reset_kill_switch()
    assert reset_info.kill_switch_engaged is False
    assert reset_info.state == SessionState.BACKGROUND


def test_security_policy_classification():
    """Test policy classification for ordinary, sensitive, and destructive actions."""
    # Ordinary
    act_type = ComputerAction(action_type=ComputerActionType.KEYBOARD_TYPE, params={"text": "Hello"})
    risk, _ = security_policy.classify_action(act_type)
    assert risk == ActionRiskLevel.ORDINARY

    # Sensitive (PowerShell system command)
    act_shell = ComputerAction(action_type=ComputerActionType.SHELL_EXECUTE, params={"command": "Stop-Service wuauserv"})
    risk, reason = security_policy.classify_action(act_shell)
    assert risk == ActionRiskLevel.SENSITIVE

    # Destructive
    act_dest = ComputerAction(action_type=ComputerActionType.SHELL_EXECUTE, params={"command": "Remove-Item C:\\Windows -Recurse"})
    risk, _ = security_policy.classify_action(act_dest)
    assert risk == ActionRiskLevel.DESTRUCTIVE


@pytest.mark.skipif(os.name != "nt", reason="Windows desktop environment required")
def test_native_windows_operations():
    """Test window listing and resolution on Windows."""
    windows = NativeOps.list_windows(visible_only=True)
    assert isinstance(windows, list)

    res = GuiOps.get_screen_size()
    assert res[0] > 0 and res[1] > 0


@pytest.mark.skipif(os.name != "nt", reason="Windows desktop environment required")
def test_screen_capture():
    """Test screenshot capture."""
    session_manager.reset_kill_switch()
    session_manager.activate_session("screenshot test")
    res = ScreenPerception.capture_screenshot(max_width=800)
    assert res.get("success") is True
    assert res.get("image_base64") is not None
    assert res.get("width") <= 800
    session_manager.terminate_session("clean up")
