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
    get_secure_sentinel_dir,
    is_safe_sentinel_path,
    session_manager,
    write_secure_sentinel,
)
from app.core.config import settings

VALID_DEVICE_TOKEN = "iris_colab_secret_2026"


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


def get_err_msg(resp) -> str:
    body = resp.json()
    if "error" in body and isinstance(body["error"], dict):
        return body["error"].get("message", "")
    return str(body.get("detail", ""))


# ==============================================================================
# SECTION 1: MANDATORY LOCAL API AUTHENTICATION & DEVICE BINDING
# ==============================================================================


def test_unauthenticated_session_activation_rejected(client):
    """Verify that unauthenticated local requests cannot activate a computer control session."""
    # 1. No token provided
    resp = client.post("/api/computer/session/start", json={"reason": "Unauthorized start"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing device authentication token" in get_err_msg(resp)

    # 2. Bogus token provided
    resp_bogus = client.post(
        "/api/computer/session/start",
        json={"reason": "Bogus token"},
        headers={"X-Computer-Auth-Token": "bogus_untrusted_token"},
    )
    assert resp_bogus.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid or untrusted device token" in get_err_msg(resp_bogus)


def test_localhost_origin_alone_is_not_authentication(client):
    """Verify that localhost Origin header is not treated as authentication."""
    headers = {"Origin": "http://localhost:5173"}
    resp = client.post("/api/computer/session/start", json={"reason": "Origin without auth"}, headers=headers)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing device authentication token" in get_err_msg(resp)


def test_authenticated_session_activation_succeeds(client):
    """Verify that valid companion/device authentication activates the session and issues a session token."""
    headers = {
        "Origin": "http://localhost:5173",
        "X-Computer-Auth-Token": VALID_DEVICE_TOKEN,
    }
    resp = client.post("/api/computer/session/start", json={"reason": "Valid auth session", "expiry_minutes": 5}, headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["state"] == "active"
    assert data["session_token"] is not None
    assert data["session_token"].startswith("cst_")


def test_telemetry_status_does_not_leak_session_token(client):
    """Verify that GET /api/computer/status never leaks the active session token."""
    session_manager.activate_session(reason="Privacy test")
    resp = client.get("/api/computer/status")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["session"]["session_token"] is None


def test_mandatory_session_token_enforced_across_all_privileged_endpoints(client):
    """Verify that all privileged endpoints reject requests lacking X-Computer-Session-Token."""
    session_manager.activate_session(reason="Token gate test")

    # 1. POST /action
    r1 = client.post("/api/computer/action", json={"action_type": ComputerActionType.WAIT.value, "params": {"seconds": 0.1}})
    assert r1.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Mandatory 'X-Computer-Session-Token' header is missing" in get_err_msg(r1)

    # 2. POST /execute-task
    r2 = client.post("/api/computer/execute-task", json={"instruction": "echo test"})
    assert r2.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Mandatory 'X-Computer-Session-Token' header is missing" in get_err_msg(r2)

    # 3. GET /windows
    r3 = client.get("/api/computer/windows")
    assert r3.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Mandatory 'X-Computer-Session-Token' header is missing" in get_err_msg(r3)

    # 4. POST /screenshot
    r4 = client.post("/api/computer/screenshot", json={})
    assert r4.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Mandatory 'X-Computer-Session-Token' header is missing" in get_err_msg(r4)

    # 5. POST /session/stop
    r5 = client.post("/api/computer/session/stop", json={})
    assert r5.status_code == status.HTTP_401_UNAUTHORIZED

    # 6. POST /session/pause
    r6 = client.post("/api/computer/session/pause")
    assert r6.status_code == status.HTTP_401_UNAUTHORIZED

    # 7. POST /session/resume
    r7 = client.post("/api/computer/session/resume")
    assert r7.status_code == status.HTTP_401_UNAUTHORIZED


def test_replayed_and_expired_session_token_rejected(client):
    """Verify that revoked, replayed, and expired session tokens are rejected with HTTP 401."""
    # Session 1: activate and terminate
    s1 = session_manager.activate_session(reason="Session 1")
    t1 = s1.session_token
    session_manager.terminate_session("Session 1 finished")

    # Replaying t1 must fail
    headers_t1 = {"X-Computer-Session-Token": t1}
    resp_replay = client.post(
        "/api/computer/action",
        json={"action_type": ComputerActionType.WAIT.value, "params": {"seconds": 0.05}},
        headers=headers_t1,
    )
    assert resp_replay.status_code == status.HTTP_401_UNAUTHORIZED
    assert "No active computer control session" in get_err_msg(resp_replay)

    # Session 2: activate new session
    s2 = session_manager.activate_session(reason="Session 2")
    t2 = s2.session_token
    assert t1 != t2

    # Old token t1 on active session 2 must fail
    resp_old = client.post(
        "/api/computer/action",
        json={"action_type": ComputerActionType.WAIT.value, "params": {"seconds": 0.05}},
        headers=headers_t1,
    )
    assert resp_old.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid, expired, or revoked" in get_err_msg(resp_old)

    # New token t2 succeeds
    headers_t2 = {"X-Computer-Session-Token": t2}
    resp_new = client.post(
        "/api/computer/action",
        json={"action_type": ComputerActionType.WAIT.value, "params": {"seconds": 0.05}},
        headers=headers_t2,
    )
    assert resp_new.status_code == status.HTTP_200_OK


def test_unauthenticated_kill_switch_reset_rejected(client):
    """Verify that resetting the emergency kill switch requires device authentication."""
    session_manager.trigger_kill_switch("test_unauth_reset")
    assert session_manager.is_kill_switch_engaged is True

    # 1. Unauthenticated reset fails
    r_unauth = client.post("/api/computer/kill-switch/reset", json={})
    assert r_unauth.status_code == status.HTTP_401_UNAUTHORIZED
    assert session_manager.is_kill_switch_engaged is True

    # 2. Authenticated reset succeeds
    r_auth = client.post(
        "/api/computer/kill-switch/reset",
        json={},
        headers={"X-Computer-Auth-Token": VALID_DEVICE_TOKEN},
    )
    assert r_auth.status_code == status.HTTP_200_OK
    assert session_manager.is_kill_switch_engaged is False


# ==============================================================================
# SECTION 2: BACKGROUND COMPANION PASSIVITY VALIDATION
# ==============================================================================


def test_background_mode_blocks_screen_observation(client):
    """Verify that screen capture is strictly rejected when in BACKGROUND mode."""
    assert session_manager.get_info().state == SessionState.BACKGROUND

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


def test_background_mode_blocks_window_inspection():
    """Verify that window enumeration and inspection are strictly rejected when in BACKGROUND mode."""
    assert session_manager.get_info().state == SessionState.BACKGROUND
    action_list = ComputerAction(action_type=ComputerActionType.WINDOW_LIST, params={})
    with pytest.raises(SessionSecurityError):
        computer_engine.execute_action(action_list)

    action_inspect = ComputerAction(action_type=ComputerActionType.INSPECT_WINDOW, params={"hwnd_or_title": "Notepad"})
    with pytest.raises(SessionSecurityError):
        computer_engine.execute_action(action_inspect)


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
# SECTION 3: KILL-SWITCH ADVERSARIAL & SENTINEL SECURITY VALIDATION
# ==============================================================================


def test_kill_switch_aborts_active_subprocess():
    """Verify that an ongoing PowerShell subprocess is instantly terminated when the kill switch triggers."""
    session_manager.activate_session(reason="Subprocess test")

    import threading
    cmd_result = {}

    def run_cmd():
        cmd_result["res"] = NativeOps.execute_powershell("Start-Sleep -Seconds 10", timeout_seconds=10.0)

    t = threading.Thread(target=run_cmd)
    t.start()
    time.sleep(0.3)

    session_manager.trigger_kill_switch(source="adversarial_test")
    t.join(timeout=2.0)

    assert not t.is_alive(), "Subprocess thread failed to terminate!"
    assert cmd_result["res"]["success"] is False
    assert "kill-switch" in cmd_result["res"]["stderr"].lower()


def test_out_of_band_sentinel_signal_file(client):
    """Verify that an out-of-band sentinel signal file triggers emergency stop."""
    s = session_manager.activate_session(reason="Sentinel file test")
    token = s.session_token
    assert session_manager.is_active is True

    # Use secure atomic sentinel creator
    write_secure_sentinel(source="electron_global_shortcut_ctrl_alt_k")

    # Subsystem should detect file and engage kill switch
    assert session_manager.is_kill_switch_engaged is True
    assert session_manager.is_active is False
    info = session_manager.get_info()
    assert info.kill_switch_engaged is True
    assert "electron_global_shortcut" in info.kill_switch_source

    # Any subsequent action is locked (HTTP 423)
    resp = client.post("/api/computer/screenshot", json={}, headers={"X-Computer-Session-Token": token})
    assert resp.status_code == status.HTTP_423_LOCKED

    # Authenticated reset clears the sentinel file
    resp_reset = client.post("/api/computer/kill-switch/reset", json={}, headers={"X-Computer-Auth-Token": VALID_DEVICE_TOKEN})
    assert resp_reset.status_code == status.HTTP_200_OK
    assert not EMERGENCY_KILL_SIGNAL_FILE.exists()
    assert session_manager.is_kill_switch_engaged is False


def test_malformed_and_stale_sentinel_files_handled_safely():
    """Verify that malformed JSON and stale timestamps in sentinel file are safely rejected."""
    session_manager.activate_session(reason="Malformed sentinel test")
    assert session_manager.is_active is True

    # 1. Non-JSON garbage
    EMERGENCY_KILL_SIGNAL_FILE.write_text("NOT_JSON_GARBAGE_BINARY\x00\xff", encoding="utf-8")
    assert session_manager.is_kill_switch_engaged is False
    assert session_manager.is_active is True

    # 2. Stale timestamp (3 days ago)
    stale_payload = json.dumps({"source": "old_test", "timestamp": time.time() - 259200})
    EMERGENCY_KILL_SIGNAL_FILE.write_text(stale_payload, encoding="utf-8")
    assert session_manager.is_kill_switch_engaged is False
    assert session_manager.is_active is True

    # 3. Far future timestamp (>1 hour in future clock skew)
    future_payload = json.dumps({"source": "future_test", "timestamp": time.time() + 3600})
    EMERGENCY_KILL_SIGNAL_FILE.write_text(future_payload, encoding="utf-8")
    assert session_manager.is_kill_switch_engaged is False
    assert session_manager.is_active is True


def test_kill_switch_blocks_new_actions_and_session_activation(client):
    """Verify that kill-switch engagement locks the subsystem from activating new sessions."""
    session_manager.trigger_kill_switch(source="test")

    with pytest.raises(KillSwitchTriggeredError):
        session_manager.activate_session("Should be blocked")

    resp = client.post(
        "/api/computer/session/start",
        json={"reason": "Should fail"},
        headers={"X-Computer-Auth-Token": VALID_DEVICE_TOKEN},
    )
    assert resp.status_code == status.HTTP_423_LOCKED


# ==============================================================================
# SECTION 4: SECURITY AUDIT & ORIGIN/TOKEN PROTECTION
# ==============================================================================


def test_untrusted_browser_origin_is_blocked(client):
    """Verify that cross-origin requests from unauthorized origins are rejected with HTTP 403."""
    headers = {
        "Origin": "http://evil-attacker-site.com",
        "X-Computer-Auth-Token": VALID_DEVICE_TOKEN,
    }
    resp = client.post("/api/computer/session/start", json={"reason": "Attack"}, headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "Untrusted origin" in get_err_msg(resp)


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
    assert "Invalid, expired, or revoked" in get_err_msg(resp)


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
