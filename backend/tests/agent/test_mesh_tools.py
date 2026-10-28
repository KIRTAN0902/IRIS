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
    assert default_registry.get("launch_mobile_app") is not None
    assert default_registry.get("capture_laptop_screen") is not None

    assert default_registry.is_mutating("ring_my_phone")
    assert default_registry.is_mutating("lock_workstation")
    assert default_registry.is_mutating("sync_clipboard")
    assert not default_registry.is_mutating("get_device_mesh_status")
    assert not default_registry.is_mutating("capture_laptop_screen")


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

    with (
        patch("app.services.mesh_service.get_windows_battery", return_value={"percent": 95, "is_charging": True}),
        patch("app.services.mesh_relay_service.is_local_windows_host", return_value=False),
        patch("app.services.mesh_relay_service.get_laptop_host_info", return_value={"is_online": False}),
    ):
        result = await tool.execute(db, user)
        assert result.success
        assert len(result.data["devices"]) == 1
        assert result.data["devices"][0]["name"] == "Pixel 8"
        assert result.data["host_battery"]["percent"] == 95
        assert "1 companion device(s) connected" in result.summary


@pytest.mark.asyncio
async def test_launch_laptop_app_tool(db: Session):
    from app.agent.tools.mesh import LaunchLaptopAppTool

    user = get_current_user(db)
    tool = LaunchLaptopAppTool()

    with patch("app.services.mesh_service.launch_windows_app", return_value={"success": True, "message": "Launched antigravity"}) as mock_launch:
        result = await tool.execute(db, user, app="antigravity")
        assert result.success
        assert "Launched antigravity" in result.summary
        mock_launch.assert_called_once_with(
            app_name="antigravity_ide",
            argument=None,
            directory=None,
            prompt=None,
            resume=False,
            conversation_id=None,
        )


@pytest.mark.asyncio
async def test_launch_antigravity_cli_tool(db: Session):
    from app.agent.tools.mesh import LaunchLaptopAppTool

    user = get_current_user(db)
    tool = LaunchLaptopAppTool()

    with patch("app.services.mesh_service.launch_windows_app", return_value={"success": True, "message": "Launched Antigravity CLI"}) as mock_launch:
        result = await tool.execute(
            db,
            user,
            app="antigravity_cli",
            directory=r"C:\kirtan\IRIS",
            prompt="fix the bug",
            resume=True,
        )
        assert result.success
        mock_launch.assert_called_once_with(
            app_name="antigravity_cli",
            argument=None,
            directory=r"C:\kirtan\IRIS",
            prompt="fix the bug",
            resume=True,
            conversation_id=None,
        )


@pytest.mark.asyncio
async def test_run_laptop_terminal_command_tool(db: Session):
    from app.agent.tools.mesh import RunLaptopTerminalCommandTool

    user = get_current_user(db)
    tool = RunLaptopTerminalCommandTool()

    fake_res = {
        "success": True,
        "returncode": 0,
        "stdout": "On branch main\nnothing to commit",
        "stderr": "",
        "command": "git status",
        "cwd": r"C:\kirtan\IRIS",
    }
    with patch("app.services.mesh_service.execute_terminal_command", return_value=fake_res):
        with patch.object(ms.hub, "broadcast", new_callable=AsyncMock):
            result = await tool.execute(db, user, command="git status")
            assert result.success
            assert "On branch main" in result.summary
            assert result.data["returncode"] == 0


@pytest.mark.asyncio
async def test_launch_mobile_app_tool(db: Session):
    from app.agent.tools.mesh import LaunchMobileAppTool

    user = get_current_user(db)
    tool = LaunchMobileAppTool()

    with patch.object(ms.hub, "broadcast", new_callable=AsyncMock) as mock_broadcast:
        result = await tool.execute(db, user, app="spotify")
        assert result.success
        assert result.data["action"] == "launch_mobile_app"
        assert result.data["app"] == "spotify"
        mock_broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_laptop_screen_tool(db: Session):
    import base64
    from app.agent.tools.mesh import CaptureLaptopScreenTool
    from app.services.vision_service import VisionExtractionResult

    user = get_current_user(db)
    tool = CaptureLaptopScreenTool()

    fake_b64 = base64.b64encode(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb").decode("utf-8")
    fake_screen = {
        "success": True,
        "image_base64": fake_b64,
        "mime_type": "image/jpeg",
        "width": 1920,
        "height": 1080,
    }
    fake_vision = VisionExtractionResult(
        summary="Laptop desktop with VS Code and Terminal open.",
        extracted_text_or_code="npm run dev\nready on port 3000",
        detected_domain="OPERATOR",
        actionable_items=[],
        memory_facts=[],
    )

    with (
        patch("app.services.mesh_relay_service.is_local_windows_host", return_value=True),
        patch("app.services.mesh_service.capture_windows_screen", return_value=fake_screen),
        patch("app.services.vision_service.vision_service.analyze_ephemeral_images", new_callable=AsyncMock, return_value=fake_vision),
        patch("app.services.vision_service.vision_service.store_visual_context"),
    ):
        result = await tool.execute(db, user, query="what is open?")
        assert result.success
        assert "VS Code and Terminal" in result.summary
        assert result.data["detected_domain"] == "OPERATOR"


