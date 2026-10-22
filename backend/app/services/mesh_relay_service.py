"""Sovereign Mesh Relay Service: One-Time Device Pairing & Cross-Network Cloud Bridge.

Provides a permanent, $0 sovereign bridge between mobile phones and laptops:
1. One-time pairing handshake (6-digit numeric PIN or QR code token).
2. Permanent cryptographic tokens stored on mobile and laptop.
3. Bidirectional cross-network relay via PostgreSQL cloud tables + instant WebSocket delivery.
4. Autonomous laptop relay daemon listening for incoming commands across any network (5G, hotel Wi-Fi, strict NAT).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import secrets
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.mesh_pairing import MeshPairing, MeshRelayMessage
from app.services import mesh_service as ms

logger = get_logger(__name__)

# Device ID identifying the primary laptop host
LAPTOP_HOST_DEVICE_ID = "laptop_host_primary"


def generate_pairing_invite(
    db: Session,
    user_id: int,
    device_name: str = "Mobile Companion",
    device_id: str | None = None,
    device_type: str = "phone_mobile",
    expires_minutes: int = 15,
) -> dict[str, Any]:
    """Generates a secure 6-digit numeric pairing code and temporary pairing invitation token."""
    code = f"{secrets.randbelow(900000) + 100000}"
    temp_token = f"iris_pair_{secrets.token_hex(24)}"
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    dev_id = device_id or f"pending_pair_{secrets.token_hex(6)}"

    invite = (
        db.query(MeshPairing)
        .filter(
            MeshPairing.user_id == user_id,
            MeshPairing.is_active == False,
        )
        .first()
    )

    if not invite:
        invite = MeshPairing(
            user_id=user_id,
            device_id=dev_id,
            device_name=device_name,
            device_type=device_type,
            pairing_code=code,
            pairing_code_expires_at=expires_at,
            pairing_token=temp_token,
            is_active=False,
        )
        db.add(invite)
    else:
        invite.device_id = dev_id
        invite.pairing_code = code
        invite.pairing_code_expires_at = expires_at
        invite.pairing_token = temp_token
        invite.device_name = device_name
        invite.device_type = device_type

    db.commit()
    db.refresh(invite)

    return {
        "pairing_code": code,
        "token": temp_token,
        "expires_at": expires_at.isoformat(),
        "device_id": dev_id,
    }


def check_invite_status(db: Session, user_id: int, token: str, device_id: str | None = None) -> dict[str, Any]:
    """Checks if a pending pairing invitation has been activated by the other device."""
    query = db.query(MeshPairing).filter(MeshPairing.user_id == user_id, MeshPairing.is_active == True)
    if token:
        pairing = query.filter(MeshPairing.pairing_token == token).first()
    elif device_id:
        pairing = query.filter(MeshPairing.device_id == device_id).first()
    else:
        pairing = None

    if pairing:
        return {
            "status": "paired",
            "device_id": pairing.device_id,
            "device_name": pairing.device_name,
            "device_type": pairing.device_type,
            "pairing_token": pairing.pairing_token,
            "paired_at": pairing.paired_at.isoformat() if pairing.paired_at else None,
        }
    return {"status": "pending"}


def verify_and_pair_device(
    db: Session,
    user_id: int,
    code_or_token: str,
    device_id: str | None = None,
    device_name: str | None = None,
    device_type: str = "phone_mobile",
) -> MeshPairing | None:
    """Verifies a 6-digit code or QR token and registers a permanent sovereign pairing."""
    now = datetime.now(UTC)

    # Look for matching pending invite or existing pairing
    clean_code = code_or_token.strip().replace(" ", "").replace("-", "")

    invite = (
        db.query(MeshPairing)
        .filter(
            MeshPairing.user_id == user_id,
            or_(
                MeshPairing.pairing_code == clean_code,
                MeshPairing.pairing_token == clean_code,
            ),
        )
        .first()
    )

    if not invite:
        logger.warning("Pairing attempt failed: Code/token '%s' not found for user %s", clean_code, user_id)
        return None

    if invite.pairing_code_expires_at and invite.pairing_code_expires_at.replace(tzinfo=UTC) < now:
        logger.warning("Pairing attempt failed: Code expired at %s", invite.pairing_code_expires_at)
        return None

    # Resolve target device_id and device_name
    # Keep the invite's device_id if verifier didn't specify one, or if verifier is laptop
    target_device_id = (
        device_id
        if (device_id and not device_id.startswith("pending_") and device_id not in ("web_client", "laptop", "desktop"))
        else invite.device_id
    )
    if target_device_id.startswith("pending_"):
        target_device_id = f"phone_{secrets.token_hex(4)}"

    target_device_name = device_name or invite.device_name or "Mobile Phone"

    # Retain the invite's token so that a device polling by token receives the active record immediately!
    perm_token = invite.pairing_token or f"iris_pair_{secrets.token_hex(24)}"

    # Check if a device with target_device_id already exists (excluding this invite)
    existing_device = (
        db.query(MeshPairing)
        .filter(
            MeshPairing.user_id == user_id,
            MeshPairing.device_id == target_device_id,
            MeshPairing.id != invite.id,
        )
        .first()
    )

    if existing_device:
        existing_device.is_active = True
        existing_device.device_name = target_device_name
        existing_device.device_type = device_type
        existing_device.pairing_token = perm_token
        existing_device.pairing_code = None
        existing_device.pairing_code_expires_at = None
        existing_device.last_seen_at = now
        active_record = existing_device
        db.delete(invite)
    else:
        invite.device_id = target_device_id
        invite.device_name = target_device_name
        invite.device_type = device_type
        invite.pairing_token = perm_token
        invite.pairing_code = None
        invite.pairing_code_expires_at = None
        invite.is_active = True
        invite.last_seen_at = now
        active_record = invite

    db.commit()
    db.refresh(active_record)
    logger.info("Device '%s' (%s) successfully paired to user %s!", target_device_name, target_device_id, user_id)

    # Broadcast device states update if loop is running
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ms.hub.broadcast_device_states())
    except RuntimeError:
        pass

    return active_record


def authenticate_device(db: Session, pairing_token: str) -> MeshPairing | None:
    """Authenticates a device by permanent pairing token and updates its last_seen timestamp."""
    if not pairing_token:
        return None

    pairing = (
        db.query(MeshPairing)
        .filter(MeshPairing.pairing_token == pairing_token, MeshPairing.is_active == True)
        .first()
    )

    if pairing:
        pairing.last_seen_at = datetime.now(UTC)
        db.commit()

    return pairing


def list_paired_devices(db: Session, user_id: int) -> list[MeshPairing]:
    """Returns all active paired devices for the user."""
    return (
        db.query(MeshPairing)
        .filter(
            MeshPairing.user_id == user_id,
            MeshPairing.is_active == True,
            ~MeshPairing.device_id.like("pending_pair_%"),
        )
        .order_by(MeshPairing.last_seen_at.desc())
        .all()
    )


def unpair_device(db: Session, user_id: int, device_id: str) -> bool:
    """Unpairs and revokes access for a device."""
    pairing = (
        db.query(MeshPairing)
        .filter(MeshPairing.user_id == user_id, MeshPairing.device_id == device_id)
        .first()
    )
    if not pairing:
        return False

    pairing.is_active = False
    db.commit()

    # Disconnect from active WebSocket if connected
    ms.hub.disconnect(device_id)
    return True


def update_device_telemetry(
    db: Session,
    device_id: str,
    battery_level: int | None = None,
    is_charging: bool | None = None,
) -> None:
    """Updates battery level and charging state for a paired device."""
    pairing = db.query(MeshPairing).filter(MeshPairing.device_id == device_id).first()
    if pairing:
        if battery_level is not None:
            pairing.battery_level = battery_level
        if is_charging is not None:
            pairing.is_charging = is_charging
        pairing.last_seen_at = datetime.now(UTC)
        db.commit()


# --- Cross-Network Cloud Relay ---


def push_relay_message(
    db: Session,
    user_id: int,
    sender_device_id: str,
    target_device_id: str | None,
    msg_type: str,
    payload: dict[str, Any],
) -> MeshRelayMessage:
    """Stores a message in the cloud relay and broadcasts to local WebSockets."""
    msg = MeshRelayMessage(
        user_id=user_id,
        sender_device_id=sender_device_id,
        target_device_id=target_device_id,
        msg_type=msg_type,
        payload=payload,
        consumed_by=[sender_device_id],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Instant broadcast to active in-memory WebSockets if available
    ws_msg = ms.MeshMessage(
        type=msg_type,
        sender_device=sender_device_id,
        target_device=target_device_id,
        payload=payload,
    )
    try:
        asyncio.create_task(ms.hub.broadcast(ws_msg, exclude_sender=True))
    except RuntimeError:
        pass  # If no running event loop in test/sync context

    return msg


def poll_relay_messages(
    db: Session,
    user_id: int,
    device_id: str,
    mark_consumed: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Polls unconsumed relay messages for a given device."""
    # Find messages intended for this device or broadcast, where device_id not in consumed_by
    # Recent messages within the last 12 hours
    cutoff = datetime.now(UTC) - timedelta(hours=12)

    messages = (
        db.query(MeshRelayMessage)
        .filter(
            MeshRelayMessage.user_id == user_id,
            MeshRelayMessage.created_at >= cutoff,
            or_(
                MeshRelayMessage.target_device_id == device_id,
                MeshRelayMessage.target_device_id.is_(None),
            ),
        )
        .order_by(MeshRelayMessage.id.asc())
        .limit(limit)
        .all()
    )

    unconsumed: list[dict[str, Any]] = []

    for m in messages:
        consumed_list: list[str] = m.consumed_by if isinstance(m.consumed_by, list) else []
        if device_id not in consumed_list and m.sender_device_id != device_id:
            unconsumed.append({
                "id": m.id,
                "msg_type": m.msg_type,
                "sender_device_id": m.sender_device_id,
                "target_device_id": m.target_device_id,
                "payload": m.payload,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })
            if mark_consumed:
                m.consumed_by = consumed_list + [device_id]

    if mark_consumed and unconsumed:
        db.commit()

    return unconsumed


# --- Sovereign Host Detection & Relay Response Waiting ---


def is_local_windows_host() -> bool:
    """Returns True if the current process is running on the local Windows workstation."""
    import os
    from pathlib import Path

    return os.name == "nt" and Path(r"C:\kirtan\IRIS").exists()


def update_host_heartbeat(db: Session, user_id: int = 1) -> None:
    """Records the laptop host heartbeat in the database so the mesh knows it is online and its battery state."""
    try:
        pairing = db.query(MeshPairing).filter(MeshPairing.device_id == LAPTOP_HOST_DEVICE_ID).first()
        battery = ms.get_windows_battery()
        bat_percent = battery.get("percent") if battery else None
        is_charging = battery.get("is_charging") if battery else None

        if not pairing:
            pairing = MeshPairing(
                user_id=user_id,
                device_id=LAPTOP_HOST_DEVICE_ID,
                device_name="Windows Laptop",
                device_type="laptop_windows",
                pairing_token="token_laptop_host_primary",
                is_active=True,
                battery_level=bat_percent,
                is_charging=is_charging,
                last_seen_at=datetime.now(UTC),
            )
            db.add(pairing)
        else:
            pairing.last_seen_at = datetime.now(UTC)
            pairing.is_active = True
            if bat_percent is not None:
                pairing.battery_level = bat_percent
            if is_charging is not None:
                pairing.is_charging = is_charging
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug("Host heartbeat update error: %s", exc)


def is_recently_active(dt: datetime | None, threshold_seconds: float = 30.0) -> bool:
    """Helper to check if a datetime is within threshold_seconds, handling naive/aware datetimes."""
    if not dt:
        return False
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        now = now.replace(tzinfo=None)
    return (now - dt).total_seconds() < threshold_seconds


def is_host_laptop_online(db: Session, user_id: int = 1) -> bool:
    """Returns True if the host laptop daemon is currently active."""
    if is_local_windows_host():
        return True
    pairing = db.query(MeshPairing).filter(MeshPairing.device_id == LAPTOP_HOST_DEVICE_ID).first()
    if pairing and pairing.last_seen_at:
        return is_recently_active(pairing.last_seen_at, threshold_seconds=30.0)
    return False


def get_laptop_host_info(db: Session, user_id: int = 1) -> dict[str, Any]:
    """Returns the host laptop's current pairing state, battery, and online status."""
    pairing = db.query(MeshPairing).filter(MeshPairing.device_id == LAPTOP_HOST_DEVICE_ID).first()
    online = False
    battery_level = None
    is_charging = None
    last_seen = None

    if is_local_windows_host():
        bat = ms.get_windows_battery()
        if bat:
            battery_level = bat.get("percent")
            is_charging = bat.get("is_charging")
        online = True
        last_seen = datetime.now(UTC).isoformat()

    if pairing:
        if not online and pairing.last_seen_at:
            online = is_recently_active(pairing.last_seen_at, threshold_seconds=30.0)
            last_seen = pairing.last_seen_at.isoformat()
        if battery_level is None:
            battery_level = pairing.battery_level
            is_charging = pairing.is_charging

    is_shield_locked = ms.is_privacy_shield_locked() if is_local_windows_host() else False

    return {
        "device_id": LAPTOP_HOST_DEVICE_ID,
        "device_name": pairing.device_name if pairing else "Windows Laptop",
        "device_type": "laptop_windows",
        "battery_level": battery_level,
        "is_charging": is_charging,
        "is_online": online,
        "is_locked": is_shield_locked,
        "last_seen_at": last_seen,
    }


async def wait_for_relay_response(
    db: Session,
    user_id: int,
    req_id: str,
    timeout_seconds: float = 20.0,
) -> dict[str, Any] | None:
    """Waits for a specific response message from the laptop host across the cloud relay."""
    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
        cutoff = datetime.now(UTC) - timedelta(minutes=2)
        messages = (
            db.query(MeshRelayMessage)
            .filter(
                MeshRelayMessage.user_id == user_id,
                MeshRelayMessage.created_at >= cutoff,
                MeshRelayMessage.sender_device_id == LAPTOP_HOST_DEVICE_ID,
                MeshRelayMessage.msg_type.in_(["TERMINAL_RESULT", "COMMAND_RESULT"]),
            )
            .order_by(MeshRelayMessage.id.desc())
            .limit(10)
            .all()
        )
        for m in messages:
            if isinstance(m.payload, dict) and m.payload.get("req_id") == req_id:
                return m.payload.get("result")
        await asyncio.sleep(0.4)
    return None


# --- Autonomous Laptop Relay Daemon ---


class LaptopRelayDaemon:
    """Background listener that processes cloud relay messages on the Windows laptop.

    Guarantees that commands sent from mobile phones anywhere in the world (e.g. 5G)
    reach the laptop and execute without requiring open router ports or dynamic tunnels.
    """

    def __init__(self, interval_seconds: float = 1.0) -> None:
        self.interval = interval_seconds
        self.running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Laptop Mesh Relay Daemon started (interval: %.1fs)", self.interval)

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Laptop Mesh Relay Daemon stopped")

    async def _run_loop(self) -> None:
        while self.running:
            try:
                await self._poll_and_execute()
            except Exception as exc:
                logger.debug("Laptop relay daemon error: %s", exc)
            await asyncio.sleep(self.interval)

    async def _poll_and_execute(self) -> None:
        # Only run on Windows laptop host
        if not is_local_windows_host():
            return

        db = SessionLocal()
        try:
            update_host_heartbeat(db, user_id=1)
            messages = poll_relay_messages(
                db=db,
                user_id=1,
                device_id=LAPTOP_HOST_DEVICE_ID,
                mark_consumed=True,
            )
            for msg in messages:
                await self._handle_message(db, msg)
        finally:
            db.close()

    async def _handle_message(self, db: Session, msg: dict[str, Any]) -> None:
        msg_type = msg.get("msg_type")
        payload = msg.get("payload", {})
        sender = msg.get("sender_device_id", "unknown")

        logger.info("Laptop received relay message: type=%s from=%s", msg_type, sender)

        if msg_type == "CLIPBOARD_SYNC":
            text = payload.get("text", "")
            if text:
                ms.hub.set_clipboard(text, sender_id=sender)

        elif msg_type == "REMOTE_COMMAND":
            cmd = payload.get("command")
            if cmd == "LOCK_PC":
                pwd = payload.get("password") or payload.get("pin")
                mode = payload.get("mode", "shield")
                locked = ms.lock_windows_pc(password=pwd, mode=mode)
                logger.info("Remote LOCK_PC executed: success=%s", locked)
            elif cmd == "UNLOCK_PC":
                pwd = payload.get("password") or payload.get("pin")
                unlocked = ms.unlock_windows_pc(password=pwd, pin=pwd)
                logger.info("Remote UNLOCK_PC executed: success=%s", unlocked)
                if sender and sender != "system":
                    push_relay_message(
                        db=db,
                        user_id=1,
                        sender_device_id=LAPTOP_HOST_DEVICE_ID,
                        target_device_id=sender,
                        msg_type="COMMAND_RESULT",
                        payload={"command": cmd, "result": unlocked},
                    )
            elif cmd in ["PING_ALERT", "PING_LAPTOP"]:
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass
                logger.info("Remote PING chime played on laptop")
            elif cmd == "DEVICE_BATTERY":
                level = payload.get("battery_level")
                charging = payload.get("is_charging")
                update_device_telemetry(db, sender, battery_level=level, is_charging=charging)
            elif cmd == "TRIGGER_CODER":
                prompt = payload.get("prompt", "")
                if prompt:
                    from app.services.autonomous_coder_service import trigger_autonomous_task

                    result = await trigger_autonomous_task(prompt)
                    logger.info("Remote Autonomous Coder triggered: %s", result)
            elif cmd == "LAUNCH_APP":
                app_name = payload.get("app", "antigravity_ide")
                arg = payload.get("argument")
                directory = payload.get("directory")
                prompt = payload.get("prompt")
                resume = payload.get("resume", False)
                conv_id = payload.get("conversation_id")
                res = ms.launch_windows_app(
                    app_name=app_name,
                    argument=arg,
                    directory=directory,
                    prompt=prompt,
                    resume=resume,
                    conversation_id=conv_id,
                )
                logger.info("Remote LAUNCH_APP executed: %s", res)
                req_id = payload.get("req_id")
                if req_id and sender and sender != "system":
                    push_relay_message(
                        db=db,
                        user_id=1,
                        sender_device_id=LAPTOP_HOST_DEVICE_ID,
                        target_device_id=sender,
                        msg_type="COMMAND_RESULT",
                        payload={"req_id": req_id, "command": cmd, "result": res},
                    )
            elif cmd in {"AGY_ATTACH_DIR", "AGY_SEND_INPUT", "AGY_SLASH_CMD", "AGY_GET_STATUS"}:
                from app.services.agy_bridge import AgyError, agy_manager

                req_id = payload.get("req_id")
                res: dict[str, Any]
                try:
                    if cmd == "AGY_ATTACH_DIR":
                        session = await asyncio.to_thread(
                            agy_manager.spawn_or_attach,
                            payload.get("directory"),
                            payload.get("alias"),
                        )
                        res = {"success": True, "session": session.to_dict()}
                    elif cmd == "AGY_SEND_INPUT":
                        key = payload.get("session_key") or agy_manager.current_session_key
                        text = payload.get("input", "")
                        if text.strip().startswith("/"):
                            result = await asyncio.to_thread(
                                agy_manager.send_raw_input, key, text
                            )
                        else:
                            result = await asyncio.to_thread(
                                agy_manager.send_prompt, key, text
                            )
                        res = {"success": True, **result}
                    elif cmd == "AGY_SLASH_CMD":
                        key = payload.get("session_key") or agy_manager.current_session_key
                        command = payload.get("command", "")
                        if not command.startswith("/"):
                            command = f"/{command}"
                        res = {
                            "success": True,
                            **await asyncio.to_thread(
                                agy_manager.send_raw_input, key, command
                            ),
                        }
                    else:
                        session = agy_manager.find_session(
                            payload.get("session_key") or agy_manager.current_session_key
                        )
                        res = (
                            {"success": True, "session": session.to_dict(),
                             "recent_output": session.recent(120)}
                            if session
                            else {"success": False, "error": "No active Antigravity session."}
                        )
                except AgyError as exc:
                    res = {"success": False, "error": str(exc)}
                logger.info("Remote %s executed: success=%s", cmd, res.get("success"))
                if req_id and sender and sender != "system":
                    push_relay_message(
                        db=db,
                        user_id=1,
                        sender_device_id=LAPTOP_HOST_DEVICE_ID,
                        target_device_id=sender,
                        msg_type="AGY_RESULT",
                        payload={"req_id": req_id, "command": cmd, "result": res},
                    )

        elif msg_type == "TERMINAL_EXEC":
            req_id = payload.get("req_id")
            cmd = payload.get("command", "")
            cwd = payload.get("working_dir")
            timeout = payload.get("timeout", 30)
            logger.info("Laptop executing remote terminal command: %s (cwd=%s)", cmd, cwd)
            res = ms.execute_terminal_command(command=cmd, cwd=cwd, timeout=timeout)
            logger.info("Laptop terminal executed: success=%s returncode=%s", res.get("success"), res.get("returncode"))
            push_relay_message(
                db=db,
                user_id=1,
                sender_device_id=LAPTOP_HOST_DEVICE_ID,
                target_device_id=sender,
                msg_type="TERMINAL_RESULT",
                payload={"req_id": req_id, "result": res},
            )

        elif msg_type == "WRITE_FILE":
            req_id = payload.get("req_id")
            fpath = payload.get("file_path", "")
            content = payload.get("content", "")
            mode = payload.get("mode", "overwrite")
            res = ms.write_laptop_file(file_path=fpath, content=content, mode=mode)
            logger.info("Laptop write file executed: %s", res.get("message"))
            if req_id and sender and sender != "system":
                push_relay_message(
                    db=db,
                    user_id=1,
                    sender_device_id=LAPTOP_HOST_DEVICE_ID,
                    target_device_id=sender,
                    msg_type="COMMAND_RESULT",
                    payload={"req_id": req_id, "command": "WRITE_FILE", "result": res},
                )

        elif msg_type == "SEARCH_FILES":
            req_id = payload.get("req_id")
            query = payload.get("query", "")
            directory = payload.get("directory")
            max_results = payload.get("max_results", 30)
            res = ms.search_laptop_files(query=query, directory=directory, max_results=max_results)
            logger.info("Laptop search files executed: %d matches", res.get("count", 0))
            if req_id and sender and sender != "system":
                push_relay_message(
                    db=db,
                    user_id=1,
                    sender_device_id=LAPTOP_HOST_DEVICE_ID,
                    target_device_id=sender,
                    msg_type="COMMAND_RESULT",
                    payload={"req_id": req_id, "command": "SEARCH_FILES", "result": res},
                )

        elif msg_type == "HANDOFF":
            state_type = payload.get("type", "UNKNOWN")
            data = payload.get("data", {})
            ms.hub.set_handoff(state_type=state_type, data=data, sender_id=sender)


relay_daemon = LaptopRelayDaemon()

