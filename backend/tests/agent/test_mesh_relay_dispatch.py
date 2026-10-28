"""Tests for Cross-Network Cloud Relay Command Dispatch & Workstation Routing."""

from __future__ import annotations

from datetime import datetime, UTC, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.agent.supervisor import get_iris_supervisor
from app.agent.tools.mesh import GetDeviceMeshStatusTool, LaunchLaptopAppTool, LockWorkstationTool
from app.core.security import get_current_user
from app.models.mesh_pairing import MeshPairing
from app.services import mesh_relay_service as mrs


def test_terminal_fast_path_cloud_dispatch(db: Session):
    user = get_current_user(db)
    supervisor = get_iris_supervisor()

    with patch.object(mrs, "is_local_windows_host", return_value=False), \
         patch.object(mrs, "is_host_laptop_online", return_value=True), \
         patch.object(mrs, "push_relay_message") as mock_push:

        resp, actions = supervisor.try_fast_path(db, user, {}, "open terminal")
        assert resp is not None
        assert "Opened Terminal" in resp.message
        assert actions[0]["success"] is True

        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        assert kwargs["target_device_id"] == mrs.LAPTOP_HOST_DEVICE_ID
        assert kwargs["msg_type"] == "REMOTE_COMMAND"
        assert kwargs["payload"]["command"] == "LAUNCH_APP"
        assert kwargs["payload"]["app"] == "terminal"


def test_terminal_fast_path_laptop_offline(db: Session):
    user = get_current_user(db)
    supervisor = get_iris_supervisor()

    with patch.object(mrs, "is_local_windows_host", return_value=False), \
         patch.object(mrs, "is_host_laptop_online", return_value=False):

        resp, actions = supervisor.try_fast_path(db, user, {}, "open terminal")
        assert resp is not None
        assert "offline or unreachable" in resp.message
        assert actions[0]["success"] is False


def test_lock_workstation_cloud_dispatch(db: Session):
    user = get_current_user(db)
    supervisor = get_iris_supervisor()

    with patch.object(mrs, "is_local_windows_host", return_value=False), \
         patch.object(mrs, "is_host_laptop_online", return_value=True), \
         patch.object(mrs, "push_relay_message") as mock_push:

        resp, actions = supervisor.try_fast_path(db, user, {}, "lock workstation")
        assert resp is not None
        assert "Workstation locked successfully" in resp.message
        assert actions[0]["success"] is True

        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        assert kwargs["payload"]["command"] == "LOCK_PC"


@pytest.mark.asyncio
async def test_mesh_status_tolerates_jitter(db: Session):
    user = get_current_user(db)
    tool = GetDeviceMeshStatusTool()

    # Create/update host pairing with heartbeat 90 seconds ago (outside 30s, inside 180s)
    pairing = db.query(MeshPairing).filter(MeshPairing.device_id == mrs.LAPTOP_HOST_DEVICE_ID).first()
    recent_time = datetime.now(UTC) - timedelta(seconds=90)
    if not pairing:
        pairing = MeshPairing(
            user_id=user.id,
            device_id=mrs.LAPTOP_HOST_DEVICE_ID,
            device_name="Windows Workstation",
            device_type="laptop_windows",
            pairing_token="token_laptop_host_primary",
            is_active=True,
            last_seen_at=recent_time,
        )
        db.add(pairing)
    else:
        pairing.last_seen_at = recent_time
    db.commit()

    with patch.object(mrs, "is_local_windows_host", return_value=False):
        result = await tool.execute(db, user)
        assert result.success is True
        assert result.data["laptop_online"] is True
        assert "ONLINE and ACTIVE" in result.summary
