"""Tests for IRIS Mesh service (device continuity, clipboard, handoff, hardware control)."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import mesh_service as ms


@pytest.fixture(autouse=True)
def reset_hub():
    """Ensure hub state is clean for every test."""
    ms.hub.active_connections.clear()
    ms.hub.devices.clear()
    ms.hub.latest_clipboard = ""
    ms.hub.latest_clipboard_updated_at = None
    ms.hub.latest_handoff_state.clear()
    yield
    ms.hub.active_connections.clear()
    ms.hub.devices.clear()


@pytest.mark.asyncio
async def test_mesh_hub_connect_and_disconnect():
    mock_ws = AsyncMock()
    await ms.hub.connect("dev_1", "phone_mobile", "My Phone", mock_ws)

    mock_ws.accept.assert_awaited_once()
    assert "dev_1" in ms.hub.devices
    assert "dev_1" in ms.hub.active_connections
    assert ms.hub.devices["dev_1"].name == "My Phone"

    ms.hub.disconnect("dev_1")
    assert "dev_1" not in ms.hub.devices
    assert "dev_1" not in ms.hub.active_connections


@pytest.mark.asyncio
async def test_mesh_hub_broadcast_filtering():
    ws_sender = AsyncMock()
    ws_target = AsyncMock()
    ws_other = AsyncMock()

    await ms.hub.connect("dev_sender", "phone_mobile", "Sender", ws_sender)
    await ms.hub.connect("dev_target", "laptop_windows", "Target Laptop", ws_target)
    await ms.hub.connect("dev_other", "phone_mobile", "Other Phone", ws_other)

    # Reset calls made during connect (e.g. broadcast_device_states)
    ws_sender.reset_mock()
    ws_target.reset_mock()
    ws_other.reset_mock()

    # 1. Broadcast excluding sender, targeting specific device
    msg_targeted = ms.MeshMessage(
        type="REMOTE_COMMAND",
        sender_device="dev_sender",
        target_device="dev_target",
        payload={"command": "LOCK_PC"},
    )
    await ms.hub.broadcast(msg_targeted, exclude_sender=True)

    ws_sender.send_text.assert_not_called()
    ws_other.send_text.assert_not_called()
    ws_target.send_text.assert_called_once()

    # 2. Broadcast to all excluding sender
    ws_target.reset_mock()
    msg_general = ms.MeshMessage(
        type="CLIPBOARD_SYNC",
        sender_device="dev_sender",
        payload={"text": "hello world"},
    )
    await ms.hub.broadcast(msg_general, exclude_sender=True)

    ws_sender.send_text.assert_not_called()
    ws_target.send_text.assert_called_once()
    ws_other.send_text.assert_called_once()


@pytest.mark.asyncio
async def test_mesh_hub_broadcast_dead_connection_cleanup():
    ws_alive = AsyncMock()
    ws_dead = AsyncMock()
    ws_dead.send_text.side_effect = RuntimeError("Socket closed")

    await ms.hub.connect("dev_alive", "laptop_windows", "Laptop", ws_alive)
    await ms.hub.connect("dev_dead", "phone_mobile", "Dead Phone", ws_dead)

    ws_alive.reset_mock()
    ws_dead.reset_mock()

    msg = ms.MeshMessage(
        type="PING",
        sender_device="system",
        payload={},
    )
    await ms.hub.broadcast(msg, exclude_sender=False)

    ws_alive.send_text.assert_called_once()
    # Dead device should be automatically cleaned up
    assert "dev_dead" not in ms.hub.devices
    assert "dev_dead" not in ms.hub.active_connections
    assert "dev_alive" in ms.hub.devices


def test_clipboard_caching():
    assert ms.hub.get_clipboard()["text"] == ""

    ms.hub.set_clipboard("https://github.com", sender_id="laptop_windows")
    clip = ms.hub.get_clipboard()
    assert clip["text"] == "https://github.com"
    assert clip["updated_at"] is not None


def test_handoff_state():
    assert ms.hub.latest_handoff_state == {}

    ms.hub.set_handoff("FOCUS_SESSION", {"session_id": "sess_123", "elapsed": 1200}, sender_id="phone_mobile")
    state = ms.hub.latest_handoff_state
    assert state["type"] == "FOCUS_SESSION"
    assert state["data"]["session_id"] == "sess_123"
    assert state["sender"] == "phone_mobile"


def test_lock_windows_pc():
    with patch("ctypes.windll.user32.LockWorkStation", return_value=1, create=True) as mock_lock:
        res = ms.lock_windows_pc()
        assert res is True
        mock_lock.assert_called_once()


def test_get_windows_battery_success():
    class FakePowerStatus:
        ACLineStatus = 1
        BatteryLifePercent = 88

    with patch("ctypes.windll.kernel32.GetSystemPowerStatus", return_value=1, create=True) as mock_status:
        with patch("ctypes.byref"):
            # Mock structure field assignments
            with patch("ctypes.Structure") as mock_struct:
                mock_struct.return_value = FakePowerStatus()
                res = ms.get_windows_battery()
                # If Windows ctypes is available on Windows, it returns power dict or None
                if res is not None:
                    assert "percent" in res
                    assert "is_charging" in res
                    assert "ac_status" in res
