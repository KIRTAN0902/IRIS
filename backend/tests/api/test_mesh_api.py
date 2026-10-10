"""Tests for IRIS Mesh API endpoints and WebSocket gateway."""

from __future__ import annotations

import io
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.services import mesh_service as ms


@pytest.fixture(autouse=True)
def reset_hub():
    ms.hub.active_connections.clear()
    ms.hub.devices.clear()
    ms.hub.latest_clipboard = ""
    yield
    ms.hub.active_connections.clear()
    ms.hub.devices.clear()


def test_clipboard_endpoints(client: TestClient):
    # 1. Initially empty
    res = client.get("/api/mesh/clipboard")
    assert res.status_code == 200
    assert res.json()["text"] == ""

    # 2. Sync new clipboard text
    res = client.post(
        "/api/mesh/clipboard",
        json={"text": "Copied from Laptop", "sender_device": "laptop_windows"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "synced"

    # 3. Verify retrieved
    res = client.get("/api/mesh/clipboard")
    assert res.status_code == 200
    assert res.json()["text"] == "Copied from Laptop"


def test_handoff_endpoints(client: TestClient):
    # 1. Set handoff state
    res = client.post(
        "/api/mesh/handoff",
        json={
            "state_type": "FOCUS_SESSION",
            "data": {"session_id": "focus_999", "task": "Study Machine Learning"},
            "sender_device": "phone_mobile",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "handed_off"

    # 2. Retrieve handoff state
    res = client.get("/api/mesh/handoff")
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FOCUS_SESSION"
    assert data["data"]["session_id"] == "focus_999"


def test_command_endpoints(client: TestClient):
    # 1. LOCK_PC
    with patch("app.services.mesh_service.lock_windows_pc", return_value=True):
        res = client.post("/api/mesh/command", json={"command": "LOCK_PC"})
        assert res.status_code == 200
        assert res.json()["command"] == "LOCK_PC"
        assert res.json()["executed"] is True

    # 2. RING_PHONE
    res = client.post(
        "/api/mesh/command",
        json={"command": "RING_PHONE", "target_device": "phone_mobile_1"},
    )
    assert res.status_code == 200
    assert res.json()["broadcast"] is True
    assert res.json()["target"] == "phone_mobile_1"


def test_file_drop_upload_and_download(client: TestClient, tmp_path):
    # Point mesh storage dir to tmp_path during test
    with patch.object(ms, "STORAGE_DIR", tmp_path):
        test_content = b"Hello from AirDrop IRIS File Drop!"
        test_file = io.BytesIO(test_content)

        # Upload
        res = client.post(
            "/api/mesh/files/upload",
            files={"file": ("airdrop_notes.txt", test_file, "text/plain")},
            data={"sender_device": "phone_mobile"},
        )
        assert res.status_code == 200
        uploaded = res.json()
        assert uploaded["filename"] == "airdrop_notes.txt"
        assert uploaded["size"] == len(test_content)

        # Download
        dl_res = client.get("/api/mesh/files/airdrop_notes.txt")
        assert dl_res.status_code == 200
        assert dl_res.content == test_content

        # Non-existent file
        err_res = client.get("/api/mesh/files/nonexistent.txt")
        assert err_res.status_code == 404

        # List vault files
        list_res = client.get("/api/mesh/files")
        assert list_res.status_code == 200
        vault_files = list_res.json()["files"]
        assert len(vault_files) == 1
        assert vault_files[0]["name"] == "airdrop_notes.txt"


def test_companion_page(client: TestClient):
    res = client.get("/api/mesh/companion")
    assert res.status_code == 200
    assert "IRIS Mesh" in res.text
    assert "Universal Clipboard" in res.text
    assert "FIND MY PHONE" in res.text

    # Also test root redirect/alias
    root_res = client.get("/companion")
    assert root_res.status_code == 200
    assert "IRIS Mesh" in root_res.text


def test_list_devices(client: TestClient):
    with patch("app.services.mesh_service.get_windows_battery", return_value={"percent": 90, "is_charging": False}):
        res = client.get("/api/mesh/devices")
        assert res.status_code == 200
        data = res.json()
        assert "devices" in data
        assert "total_connected" in data
        assert data["host_power"]["percent"] == 90


def test_mesh_websocket_lifecycle(client: TestClient):
    with client.websocket_connect(
        "/api/mesh/ws?device_id=phone_test_1&device_type=phone_mobile&name=TesterPhone"
    ) as websocket:
        # 1. Device registered in hub
        assert "phone_test_1" in ms.hub.devices
        assert ms.hub.devices["phone_test_1"].name == "TesterPhone"

        # 2. Send CLIPBOARD_SYNC message
        websocket.send_json({
            "type": "CLIPBOARD_SYNC",
            "payload": {"text": "Syncing from websocket test"},
        })

        # Check internal clipboard updated
        assert ms.hub.latest_clipboard == "Syncing from websocket test"

        # 3. Send PING
        websocket.send_json({"type": "PING"})

    # After websocket context exits, device should be disconnected
    assert "phone_test_1" not in ms.hub.devices
