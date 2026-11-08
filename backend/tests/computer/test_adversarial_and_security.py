"""Adversarial security, kill-switch, and background companion verification test suite."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.computer.contracts import ActionRiskLevel, ComputerAction, ComputerActionType, SessionState
from app.computer.engine import computer_engine
from app.computer.native_ops import NativeOps
from app.computer.security import security_policy
from app.computer.session import (
    EMERGENCY_KILL_SIGNAL_FILE,
    KillSwitchTriggeredError,
    SessionSecurityError,
    session_manager,
)


@pytest.fixture(autouse=True)
def clean_subsystem_state():
    """Ensure clean background state before and after each test."""
    session_manager.reset_kill_switch()
    if EMERGENCY_KILL_SIGNAL_FILE.exists():
        try:
            EMERGENCY_KILL_SIGNAL_FILE.unlink()
        except Exception:
            pass
    yield
    session_manager.reset_kill_switch()
    if EMERGENCY_KILL_SIGNAL_FILE.exists():
        try:
            EMERGENCY_KILL_SIGNAL_FILE.unlink()
        except Exception:
            pass


# ==============================================================================
# SECTION 2: BACKGROUND COMPANION PASSIVITY VALIDATION
# ==============================================================================


def get_err_msg(resp) -> str:
    body = resp.json()
    if "error" in body and isinstance(body["error"], dict):
        return body["error"].get("message", "")
    return str(body.get("detail", ""))


def test_background_mode_blocks_screen_observation(client):
    """Verify that screen capture is strictly rejected when in BACKGROUND mode."""
    assert session_manager.get_info().state == SessionState.BACKGROUND

    # API screenshot endpoint
    resp = client.post("/api/computer/screenshot", json={"max_width": 800, "quality": 50})
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "Screen observation is disabled in background mode" in get_err_msg(resp)

    # Direct engine action
    action = ComputerAction(action_type=ComputerActionType.OBSERVE_SCREEN, params={})
    with pytest.raises(SessionSecurityError):
        computer_engine.execute_action(action)


def test_background_mode_blocks_clipboard_access():
    """Verify that clipboard reading and writing are strictly rejected when in BACKGROUND mode."""
    assert session_manager.get_info().state == SessionState.BACKGROUND

    # Clipboard Read
    action_read = ComputerAction(action_type=ComputerActionType.CLIPBOARD_READ, params={})
    with pytest.raises(SessionSecurityError):
        computer_engine.execute_action(action_read)

    # Clipboard Write
    action_write = ComputerAction(action_type=ComputerActionType.CLIPBOARD_WRITE, params={"text": "leak"})
    with pytest.raises(SessionSecurityError):
        computer_engine.execute_action(action_write)


def test_background_mode_blocks_window_inspection(client):
    """Verify that window enumeration and inspection are strictly rejected when in BACKGROUND mode."""
    assert session_manager.get_info().state == SessionState.BACKGROUND

    # GET /windows requires active session
    resp = client.get("/api/computer/windows")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "Desktop access is disabled in background mode" in get_err_msg(resp)


def test_background_mode_blocks_keyboard_and_mouse_actions():
    """Verify that typing and mouse clicks are blocked in background mode."""
    assert session_manager.get_info().state == SessionState.BACKGROUND

    # Type action
    action_type = ComputerAction(action_type=ComputerActionType.KEYBOARD_TYPE, params={"text": "blocked"})
    with pytest.raises(SessionSecurityError):
        computer_engine.execute_action(action_type)

    # Click action
    action_click = ComputerAction(action_type=ComputerActionType.MOUSE_CLICK, params={"x": 100, "y": 100})
    with pytest.raises(SessionSecurityError):
        computer_engine.execute_action(action_click)


# ==============================================================================
# SECTION 3: KILL-SWITCH ADVERSARIAL VALIDATION
# ==============================================================================


def test_kill_switch_aborts_active_subprocess():
    """Verify that an ongoing PowerShell subprocess is instantly terminated when the kill switch triggers."""
    session_manager.activate_session(reason="Subprocess test")

    # Start a 10-second sleep command in a background thread
    import threading
    cmd_result = {}

    def run_cmd():
        cmd_result["res"] = NativeOps.execute_powershell("Start-Sleep -Seconds 10", timeout_seconds=10.0)

    t = threading.Thread(target=run_cmd)
    t.start()
    time.sleep(0.3)

    # Trigger emergency stop while command is still sleeping
    session_manager.trigger_kill_switch(source="adversarial_test")
    t.join(timeout=2.0)

    assert not t.is_alive(), "Subprocess thread failed to terminate!"
    assert cmd_result["res"]["success"] is False
    assert "kill-switch" in cmd_result["res"]["stderr"].lower()


def test_out_of_band_sentinel_signal_file(client):
    """Verify that an out-of-band sentinel signal file (written by Electron or OS) triggers emergency stop."""
    session_manager.activate_session(reason="Sentinel file test")
    assert session_manager.is_active is True

    # Simulate Electron global shortcut creating sentinel file directly on disk
    EMERGENCY_KILL_SIGNAL_FILE.write_text(
        json.dumps({"source": "electron_global_shortcut_ctrl_alt_k", "timestamp": time.time()}),
        encoding="utf-8",
    )

    # Subsystem should detect file and engage kill switch
    assert session_manager.is_kill_switch_engaged is True
    assert session_manager.is_active is False
    info = session_manager.get_info()
    assert info.kill_switch_engaged is True
    assert "electron_global_shortcut" in info.kill_switch_source

    # Any subsequent action is locked (HTTP 423)
    resp = client.post("/api/computer/screenshot", json={})
    assert resp.status_code == status.HTTP_423_LOCKED

    # Reset clears the sentinel file
    session_manager.reset_kill_switch()
    assert not EMERGENCY_KILL_SIGNAL_FILE.exists()
    assert session_manager.is_kill_switch_engaged is False


def test_kill_switch_blocks_new_actions_and_session_activation(client):
    """Verify that kill-switch engagement locks the subsystem from activating new sessions."""
    session_manager.trigger_kill_switch(source="test")

    with pytest.raises(KillSwitchTriggeredError):
        session_manager.activate_session("Should be blocked")

    resp = client.post("/api/computer/session/start", json={"reason": "Should fail"})
    assert resp.status_code == status.HTTP_423_LOCKED


# ==============================================================================
# SECTION 4: SECURITY AUDIT & ORIGIN/TOKEN PROTECTION
# ==============================================================================


def test_untrusted_browser_origin_is_blocked(client):
    """Verify that cross-origin requests from unauthorized origins are rejected with HTTP 403."""
    headers = {"Origin": "http://evil-attacker-site.com"}
    resp = client.post("/api/computer/session/start", json={"reason": "Attack"}, headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "Untrusted origin" in get_err_msg(resp)


def test_trusted_browser_origin_is_allowed(client):
    """Verify that requests from authorized frontend origins (e.g. Vite dev or Electron) succeed."""
    headers = {"Origin": "http://localhost:5173"}
    resp = client.post("/api/computer/session/start", json={"reason": "Valid UI request"}, headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["state"] == "active"


def test_forged_session_token_is_rejected(client):
    """Verify that providing an invalid/forged X-Computer-Session-Token header results in HTTP 401."""
    session_manager.activate_session(reason="Auth test")

    headers = {
        "Origin": "http://localhost:5173",
        "X-Computer-Session-Token": "cst_forged_token_0000000000000000",
    }
    resp = client.post(
        "/api/computer/action",
        json={"action_type": ComputerActionType.WAIT.value, "params": {"seconds": 0.1}},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid, expired, or forged" in get_err_msg(resp)


def test_valid_session_token_succeeds(client):
    """Verify that requests with the genuine session token succeed."""
    info = session_manager.activate_session(reason="Valid token test")
    valid_token = info.session_token
    assert valid_token is not None

    headers = {
        "Origin": "http://localhost:5173",
        "X-Computer-Session-Token": valid_token,
    }
    resp = client.post(
        "/api/computer/action",
        json={"action_type": ComputerActionType.WAIT.value, "params": {"seconds": 0.05}},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["success"] is True


def test_approval_token_single_use_and_replay_prevention():
    """Verify that sensitive action approval tokens are strictly single-use and cannot be replayed."""
    action = ComputerAction(
        action_type=ComputerActionType.SHELL_EXECUTE,
        params={"command": "Stop-Service Spooler"},
    )
    token = security_policy.issue_approval_token(action, "Stop service confirmation")

    # First consumption: valid
    assert security_policy.verify_and_consume_token(token, action) is True

    # Replay attempt: must fail
    assert security_policy.verify_and_consume_token(token, action) is False


def test_approval_token_expiration():
    """Verify that approval tokens expire after their TTL."""
    action = ComputerAction(
        action_type=ComputerActionType.SHELL_EXECUTE,
        params={"command": "Stop-Service Spooler"},
    )
    # Issue with 0.05 second TTL
    token = security_policy.issue_approval_token(action, "Expiring token", ttl_seconds=0.05)
    time.sleep(0.08)

    # Verification must fail due to expiration
    assert security_policy.verify_and_consume_token(token, action) is False


def test_approval_token_parameter_tampering_prevention():
    """Verify that an approval token issued for one command cannot be applied to a different command."""
    action_orig = ComputerAction(
        action_type=ComputerActionType.SHELL_EXECUTE,
        params={"command": "Stop-Service SafeService"},
    )
    token = security_policy.issue_approval_token(action_orig, "Safe confirmation")

    action_tampered = ComputerAction(
        action_type=ComputerActionType.SHELL_EXECUTE,
        params={"command": "Stop-Service CriticalService"},
    )

    # Should reject due to parameter mismatch
    assert security_policy.verify_and_consume_token(token, action_tampered) is False
