"""Tests for IRIS Mesh agent tools (ring_my_phone, lock_workstation, sync_clipboard, get_device_mesh_status)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from app.agent.registry import default_registry
from app.agent.tools.mesh import (
    GetDeviceMeshStatusTool,
    LockWorkstationTool,
    RingMyPhoneTool,
    SyncClipboardTool,
)
from app.core.security import get_current_user
from app.services import mesh_service as ms


@pytest.fixture(autouse=True)
def reset_hub():
    ms.hub.active_connections.clear()
    ms.hub.devices.clear()
    ms.hub.latest_clipboard = ""
    yield
    ms.hub.active_connections.clear()
    ms.hub.devices.clear()


def test_mesh_tools_registered():
    assert default_registry.get("ring_my_phone") is not None
    assert default_registry.get("lock_workstation") is not None
    assert default_registry.get("sync_clipboard") is not None
    assert default_registry.get("get_device_mesh_status") is not None

    assert default_registry.is_mutating("ring_my_phone")
    assert default_registry.is_mutating("lock_workstation")
    assert default_registry.is_mutating("sync_clipboard")
    assert not default_registry.is_mutating("get_device_mesh_status")


@pytest.mark.asyncio
async def test_ring_my_phone_tool(db: Session):
    user = get_current_user(db)
    tool = RingMyPhoneTool()

    with patch.object(ms.hub, "broadcast", new_callable=AsyncMock) as mock_broadcast:
        result = await tool.execute(db, user)
        assert result.success
        assert result.data["alert"] == "RING_PHONE"
        assert "Triggered ring alert" in result.summary
        mock_broadcast.assert_awaited_once()
        msg = mock_broadcast.call_args[0][0]
        assert msg.type == "REMOTE_COMMAND"
        assert msg.payload.get("command") == "RING_PHONE"


@pytest.mark.asyncio
async def test_lock_workstation_tool(db: Session):
    user = get_current_user(db)
    tool = LockWorkstationTool()

    with patch("app.services.mesh_service.lock_windows_pc", return_value=True) as mock_lock:
        result = await tool.execute(db, user)
        assert result.success
        assert result.data["locked"] is True
        assert "Locked Windows laptop" in result.summary
        mock_lock.assert_called_once()


@pytest.mark.asyncio
async def test_sync_clipboard_tool(db: Session):
    user = get_current_user(db)
    tool = SyncClipboardTool()

    with patch.object(ms.hub, "broadcast", new_callable=AsyncMock) as mock_broadcast:
        result = await tool.execute(db, user, text="git commit -m 'mesh features'")
        assert result.success
        assert result.data["length"] == len("git commit -m 'mesh features'")
        assert ms.hub.latest_clipboard == "git commit -m 'mesh features'"
        mock_broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_device_mesh_status_tool(db: Session):
    user = get_current_user(db)
    tool = GetDeviceMeshStatusTool()

    # Pre-populate device
    mock_ws = AsyncMock()
    await ms.hub.connect("phone_1", "phone_mobile", "Pixel 8", mock_ws)

    with patch("app.services.mesh_service.get_windows_battery", return_value={"percent": 95, "is_charging": True}):
        result = await tool.execute(db, user)
        assert result.success
        assert len(result.data["devices"]) == 1
        assert result.data["devices"][0]["name"] == "Pixel 8"
        assert result.data["host_battery"]["percent"] == 95
        assert "1 device(s) connected" in result.summary
