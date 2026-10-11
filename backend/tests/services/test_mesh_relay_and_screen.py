"""Unit tests for Sovereign Mesh Relay Service and WebRTC Screen Stream Service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services import mesh_relay_service as mrs
from app.services import screen_stream_service as sss


def test_mesh_relay_service_pairing_workflow(db: Session):
    user = get_current_user(db)

    # 1. Generate pairing invite
    invite = mrs.generate_pairing_invite(db, user.id, device_name="Test Phone")
    assert "pairing_code" in invite
    assert len(invite["pairing_code"]) == 6
    code = invite["pairing_code"]

    # 2. Verify with code
    pairing = mrs.verify_and_pair_device(
        db=db,
        user_id=user.id,
        code_or_token=code,
        device_id="device_test_phone_99",
        device_name="Test Phone 99",
        device_type="phone_mobile",
    )
    assert pairing is not None
    assert pairing.device_id == "device_test_phone_99"
    assert pairing.is_active is True
    assert pairing.pairing_token.startswith("iris_pair_")

    # 3. Authenticate device
    auth_device = mrs.authenticate_device(db, pairing.pairing_token)
    assert auth_device is not None
    assert auth_device.id == pairing.id

    # 4. Update telemetry
    mrs.update_device_telemetry(db, "device_test_phone_99", battery_level=88, is_charging=True)
    db.refresh(pairing)
    assert pairing.battery_level == 88
    assert pairing.is_charging is True

    # 5. List paired devices
    devices = mrs.list_paired_devices(db, user.id)
    assert len(devices) >= 1
    assert any(d.device_id == "device_test_phone_99" for d in devices)

    # 6. Push and poll relay messages
    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id="device_test_phone_99",
        target_device_id="laptop_host_primary",
        msg_type="TEST_RELAY",
        payload={"msg": "Hello Cloud Relay"},
    )

    poll_results = mrs.poll_relay_messages(
        db=db,
        user_id=user.id,
        device_id="laptop_host_primary",
        mark_consumed=True,
    )
    assert len(poll_results) >= 1
    assert any(m["payload"].get("msg") == "Hello Cloud Relay" for m in poll_results)

    # Polling again should yield 0 new messages because it was marked consumed
    poll_results_2 = mrs.poll_relay_messages(
        db=db,
        user_id=user.id,
        device_id="laptop_host_primary",
        mark_consumed=True,
    )
    assert not any(m["payload"].get("msg") == "Hello Cloud Relay" for m in poll_results_2)

    # 7. Unpair device
    unpair_res = mrs.unpair_device(db, user.id, "device_test_phone_99")
    assert unpair_res is True
    active_devices_after = mrs.list_paired_devices(db, user.id)
    assert not any(d.device_id == "device_test_phone_99" for d in active_devices_after)


def test_screen_stream_service_capabilities():
    # 1. Screen dimensions
    w, h = sss.get_screen_dimensions()
    assert w > 0
    assert h > 0

    # 2. Snapshot capture
    jpeg_data = sss.get_screen_jpeg_bytes(quality=40, scale_factor=3)
    assert jpeg_data is not None
    assert len(jpeg_data) > 500

    # 3. Input injection (safe simulated actions)
    assert sss.inject_mouse_event(action="move", x_ratio=0.5, y_ratio=0.5) is True
    assert sss.inject_keyboard_event(text="iris") is True
