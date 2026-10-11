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
    expires_minutes: int = 15,
) -> dict[str, Any]:
    """Generates a secure 6-digit numeric pairing code and temporary pairing invitation token."""
    # Generate 6-digit numeric PIN
    code = f"{secrets.randbelow(900000) + 100000}"
    temp_token = secrets.token_hex(20)
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)

    # Check if a pending invite already exists for this user/slot, otherwise create
    invite = (
        db.query(MeshPairing)
        .filter(
            MeshPairing.user_id == user_id,
            MeshPairing.device_id.like("pending_pair_%"),
            MeshPairing.is_active == False,
        )
        .first()
    )

    if not invite:
        invite = MeshPairing(
            user_id=user_id,
            device_id=f"pending_pair_{secrets.token_hex(6)}",
            device_name=device_name,
            device_type="phone_mobile",
            pairing_code=code,
            pairing_code_expires_at=expires_at,
            pairing_token=temp_token,
            is_active=False,
        )
        db.add(invite)
    else:
        invite.pairing_code = code
        invite.pairing_code_expires_at = expires_at
        invite.pairing_token = temp_token
        invite.device_name = device_name

    db.commit()
    db.refresh(invite)

    # Generate QR Code SVG URI if segno is installed
    qr_svg_uri = ""
    try:
        import segno

        qr = segno.make(f"iris://mesh/pair?code={code}&token={temp_token}")
        qr_svg_uri = qr.svg_data_uri(scale=5)
    except Exception as exc:
        logger.debug("QR generation error: %s", exc)

    return {
        "pairing_code": code,
        "token": temp_token,
        "expires_at": expires_at.isoformat(),
        "qr_svg_uri": qr_svg_uri,
    }


def verify_and_pair_device(
    db: Session,
    user_id: int,
    code_or_token: str,
    device_id: str,
    device_name: str,
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

    # Check if this exact device_id was already paired before
    existing_device = (
        db.query(MeshPairing)
        .filter(MeshPairing.user_id == user_id, MeshPairing.device_id == device_id)
        .first()
    )

    perm_token = f"iris_pair_{secrets.token_hex(24)}"

    if existing_device:
        existing_device.is_active = True
        existing_device.device_name = device_name
        existing_device.device_type = device_type
        existing_device.pairing_token = perm_token
        existing_device.pairing_code = None
        existing_device.pairing_code_expires_at = None
        existing_device.last_seen_at = now
        active_record = existing_device
        # Remove old invite placeholder if it was a different row
        if invite.id != existing_device.id:
            db.delete(invite)
    else:
        invite.device_id = device_id
        invite.device_name = device_name
        invite.device_type = device_type
        invite.pairing_token = perm_token
        invite.pairing_code = None
        invite.pairing_code_expires_at = None
        invite.is_active = True
        invite.last_seen_at = now
        active_record = invite

    db.commit()
    db.refresh(active_record)
    logger.info("Device '%s' (%s) successfully paired to user %s!", device_name, device_id, user_id)

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


# --- Autonomous Laptop Relay Daemon ---


class LaptopRelayDaemon:
    """Background listener that processes cloud relay messages on the Windows laptop.
    
    Guarantees that commands sent from mobile phones anywhere in the world (e.g. 5G)
    reach the laptop and execute without requiring open router ports or dynamic tunnels.
    """

    def __init__(self, interval_seconds: float = 1.5) -> None:
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
        # Default user 1 (Kirtan)
        db = SessionLocal()
        try:
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
                locked = ms.lock_windows_pc()
                logger.info("Remote LOCK_PC executed: success=%s", locked)
            elif cmd == "DEVICE_BATTERY":
                level = payload.get("battery_level")
                charging = payload.get("is_charging")
                update_device_telemetry(db, sender, battery_level=level, is_charging=charging)
            elif cmd == "TRIGGER_CODER":
                # Autonomous Antigravity coder triggered remotely
                prompt = payload.get("prompt", "")
                if prompt:
                    from app.services.autonomous_coder_service import trigger_autonomous_task
                    result = await trigger_autonomous_task(prompt)
                    logger.info("Remote Autonomous Coder triggered: %s", result)
            elif cmd == "LAUNCH_APP":
                app_name = payload.get("app", "antigravity")
                arg = payload.get("argument")
                res = ms.launch_windows_app(app_name=app_name, argument=arg)
                logger.info("Remote LAUNCH_APP executed: %s", res)

        elif msg_type == "HANDOFF":
            state_type = payload.get("type", "UNKNOWN")
            data = payload.get("data", {})
            ms.hub.set_handoff(state_type=state_type, data=data, sender_id=sender)


relay_daemon = LaptopRelayDaemon()
