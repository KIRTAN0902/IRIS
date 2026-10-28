"""FastAPI routes, WebSocket gateway, Sovereign Relay, and Screen Mirroring for IRIS Mesh."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.services import mesh_relay_service as mrs
from app.services import mesh_service as ms
from app.services import screen_stream_service as sss

router = APIRouter(prefix="/mesh", tags=["mesh"])


# --- Schemas ---


class ClipboardSyncRequest(BaseModel):
    text: str = Field(..., description="Text content to sync across devices")
    sender_device: str = "web_client"


class RemoteCommandRequest(BaseModel):
    command: str = Field(..., description="'LOCK_PC', 'RING_PHONE', 'GET_BATTERY', 'TRIGGER_CODER'")
    target_device: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class HandoffRequest(BaseModel):
    state_type: str = Field(..., description="'FOCUS_SESSION', 'READING_TAB', 'TASK'")
    data: dict[str, Any] = Field(..., description="State payload to hand off")
    sender_device: str = "web_client"


class PairingCodeRequest(BaseModel):
    device_name: str = "Mobile Companion"
    device_id: str | None = None
    device_type: str = "phone_mobile"


class PairingVerifyRequest(BaseModel):
    code: str = Field(..., description="6-digit pairing code or QR token")
    device_id: str | None = None
    device_name: str | None = "Mobile Phone"
    device_type: str = "phone_mobile"


class DeviceTelemetryRequest(BaseModel):
    device_id: str
    device_name: str | None = None
    device_type: str = "phone_mobile"
    battery_level: int | None = None
    is_charging: bool | None = None
    pairing_token: str | None = None


class RelaySendRequest(BaseModel):
    sender_device_id: str
    target_device_id: str | None = None
    msg_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class WebRTCOfferRequest(BaseModel):
    session_id: str
    sdp: str
    type: str = "offer"


class WebRTCCandidateRequest(BaseModel):
    session_id: str
    candidate: dict[str, Any]


class RemoteMouseRequest(BaseModel):
    action: str = "click"  # "move", "click", "down", "up", "double_click", "wheel"
    x: float = 0.5
    y: float = 0.5
    button: str = "left"
    delta: int = 0


class RemoteKeyboardRequest(BaseModel):
    text: str | None = None
    key: str | None = None


# --- One-Time Sovereign Pairing Endpoints ---


@router.post("/pair/code")
def create_pairing_code(
    req: PairingCodeRequest = PairingCodeRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Generates a secure 6-digit numeric PIN code for one-time pairing."""
    invite = mrs.generate_pairing_invite(
        db=db,
        user_id=user.id,
        device_name=req.device_name,
        device_id=req.device_id,
        device_type=req.device_type,
        expires_minutes=15,
    )
    return invite


@router.get("/pair/status")
def get_pairing_status(
    token: str = Query(..., description="Pending invite token"),
    device_id: str | None = Query(None, description="Optional client device ID"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Polls if a pending pairing invitation has been verified and activated."""
    return mrs.check_invite_status(db=db, user_id=user.id, token=token, device_id=device_id)


@router.post("/pair/verify")
async def verify_device_pairing(
    req: PairingVerifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Verifies 6-digit pairing code or QR token and registers permanent sovereign device pairing."""
    pairing = mrs.verify_and_pair_device(
        db=db,
        user_id=user.id,
        code_or_token=req.code,
        device_id=req.device_id,
        device_name=req.device_name,
        device_type=req.device_type,
    )
    if not pairing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired pairing code.",
        )
    return {
        "status": "paired",
        "device_id": pairing.device_id,
        "device_name": pairing.device_name,
        "device_type": pairing.device_type,
        "pairing_token": pairing.pairing_token,
        "paired_at": pairing.paired_at.isoformat() if pairing.paired_at else None,
    }


@router.get("/pair/devices")
def list_paired_devices(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Lists all active paired sovereign mesh devices and laptop host info."""
    devices = mrs.list_paired_devices(db=db, user_id=user.id)
    laptop_info = mrs.get_laptop_host_info(db=db, user_id=user.id)
    now = datetime.now(UTC)

    paired_list = []
    for d in devices:
        if d.device_id == mrs.LAPTOP_HOST_DEVICE_ID:
            continue
        is_online = mrs.is_recently_active(d.last_seen_at, threshold_seconds=35.0)
        paired_list.append({
            "id": d.id,
            "device_id": d.device_id,
            "device_name": d.device_name,
            "device_type": d.device_type,
            "battery_level": d.battery_level,
            "is_charging": d.is_charging,
            "is_online": is_online,
            "paired_at": d.paired_at.isoformat() if d.paired_at else None,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        })

    return {
        "laptop_host": laptop_info,
        "paired_devices": paired_list,
        "count": len(paired_list),
    }


@router.post("/telemetry")
def report_device_telemetry(
    req: DeviceTelemetryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Updates device battery level, charging status, and online heartbeat."""
    from app.models.mesh_pairing import MeshPairing

    now = datetime.now(UTC)
    pairing = db.query(MeshPairing).filter(
        MeshPairing.user_id == user.id,
        MeshPairing.device_id == req.device_id,
    ).first()

    if pairing:
        pairing.last_seen_at = now
        pairing.is_active = True
        if req.battery_level is not None:
            pairing.battery_level = req.battery_level
        if req.is_charging is not None:
            pairing.is_charging = req.is_charging
        if req.device_name:
            pairing.device_name = req.device_name
        db.commit()
    else:
        pairing = MeshPairing(
            user_id=user.id,
            device_id=req.device_id,
            device_name=req.device_name or ("Mobile Companion" if "phone" in req.device_type else "Client Device"),
            device_type=req.device_type,
            pairing_token=req.pairing_token or f"token_{req.device_id}",
            is_active=True,
            battery_level=req.battery_level,
            is_charging=req.is_charging,
            last_seen_at=now,
        )
        db.add(pairing)
        db.commit()

    return {
        "status": "ok",
        "device_id": req.device_id,
        "battery_level": req.battery_level,
        "is_charging": req.is_charging,
        "last_seen_at": now.isoformat(),
    }


@router.delete("/pair/{device_id}")
def revoke_paired_device(
    device_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Revokes and unpairs a device from the sovereign mesh."""
    success = mrs.unpair_device(db=db, user_id=user.id, device_id=device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found.")
    return {"status": "unpaired", "device_id": device_id}


# --- Cross-Network Cloud Relay Endpoints ---


@router.post("/relay/send")
def send_cloud_relay_message(
    req: RelaySendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Sends a message across networks through the sovereign cloud relay."""
    msg = mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id=req.sender_device_id,
        target_device_id=req.target_device_id,
        msg_type=req.msg_type,
        payload=req.payload,
    )
    return {"status": "relayed", "msg_id": msg.id}


@router.get("/relay/poll")
def poll_cloud_relay_messages(
    device_id: str = Query(..., description="Device ID polling for messages"),
    token: str | None = Query(None, description="Pairing token for authentication"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Polls unconsumed relay messages for a device across cellular/Wi-Fi."""
    if token:
        mrs.authenticate_device(db=db, pairing_token=token)

    messages = mrs.poll_relay_messages(
        db=db,
        user_id=user.id,
        device_id=device_id,
        mark_consumed=True,
    )
    return {"messages": messages, "count": len(messages)}


# --- Step 2: WebRTC Screen Mirroring & Remote Control ---


@router.post("/screen/webrtc/offer")
async def handle_webrtc_screen_offer(
    req: WebRTCOfferRequest,
    user: User = Depends(current_user),
):
    """Processes an incoming WebRTC SDP Offer from mobile and returns SDP Answer."""
    try:
        answer = await sss.stream_manager.handle_offer(
            session_id=req.session_id,
            sdp_offer=req.sdp,
            sdp_type=req.type,
        )
        return answer
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"WebRTC negotiation error: {exc}")


@router.post("/screen/webrtc/candidate")
async def handle_webrtc_candidate(
    req: WebRTCCandidateRequest,
    user: User = Depends(current_user),
):
    """Adds an ICE candidate to the active peer connection."""
    await sss.stream_manager.add_ice_candidate(req.session_id, req.candidate)
    return {"status": "candidate_received"}


@router.delete("/screen/webrtc/session/{session_id}")
async def close_webrtc_session(
    session_id: str,
    user: User = Depends(current_user),
):
    """Closes an active WebRTC desktop streaming session."""
    await sss.stream_manager.close_session(session_id)
    return {"status": "closed", "session_id": session_id}


@router.get("/screen/snapshot")
def get_screen_snapshot(
    quality: int = Query(70, ge=10, le=100),
    scale: int = Query(2, ge=1, le=4),
):
    """Direct JPEG snapshot of primary monitor for fast fallback / preview."""
    jpeg_bytes = sss.get_screen_jpeg_bytes(quality=quality, scale_factor=scale)
    if not jpeg_bytes:
        raise HTTPException(status_code=500, detail="Could not capture screen.")
    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.post("/screen/input/mouse")
def remote_mouse_control(
    req: RemoteMouseRequest,
    user: User = Depends(current_user),
):
    """Executes remote mouse actions on Windows host from mobile touch/click."""
    success = sss.inject_mouse_event(
        action=req.action,
        x_ratio=req.x,
        y_ratio=req.y,
        button=req.button,
        wheel_delta=req.delta,
    )
    return {"success": success, "action": req.action}


@router.post("/screen/input/keyboard")
def remote_keyboard_control(
    req: RemoteKeyboardRequest,
    user: User = Depends(current_user),
):
    """Injects remote text typing or keystrokes on Windows host."""
    success = sss.inject_keyboard_event(text=req.text, key=req.key)
    return {"success": success}


# --- WebSocket Gateway ---


@router.websocket("/ws")
async def mesh_websocket_endpoint(
    websocket: WebSocket,
    device_id: str = Query(..., description="Unique client ID (e.g. 'phone_mobile_1')"),
    device_type: str = Query("phone_mobile", description="'laptop_windows' or 'phone_mobile'"),
    name: str = Query("Mobile Phone", description="Friendly device name"),
    token: str | None = Query(None, description="Optional pairing token"),
):
    """Real-time bi-directional WebSocket gateway between phone and laptop."""
    await ms.hub.connect(device_id=device_id, device_type=device_type, name=name, websocket=websocket)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
                msg_type = data.get("type", "UNKNOWN")
                payload = data.get("payload", {})

                if msg_type == "CLIPBOARD_SYNC":
                    text = payload.get("text", "")
                    ms.hub.set_clipboard(text, sender_id=device_id)
                    # Broadcast to other devices
                    msg = ms.MeshMessage(
                        type="CLIPBOARD_SYNC",
                        sender_device=device_id,
                        payload={"text": text},
                    )
                    await ms.hub.broadcast(msg, exclude_sender=True)

                elif msg_type == "REMOTE_COMMAND":
                    cmd = payload.get("command")
                    if cmd == "LOCK_PC":
                        pwd = payload.get("password") or payload.get("pin")
                        mode = payload.get("mode", "shield")
                        ms.lock_windows_pc(password=pwd, mode=mode)
                    elif cmd == "UNLOCK_PC":
                        pwd = payload.get("password") or payload.get("pin")
                        ms.unlock_windows_pc(password=pwd, pin=pwd)
                    elif cmd == "DEVICE_BATTERY":
                        if device_id in ms.hub.devices:
                            ms.hub.devices[device_id].battery_level = payload.get("battery_level")
                            ms.hub.devices[device_id].is_charging = payload.get("is_charging")
                            await ms.hub.broadcast_device_states()
                    elif cmd == "LAUNCH_APP":
                        if mrs.is_local_windows_host():
                            res = ms.launch_windows_app(
                                app_name=payload.get("app", "terminal"),
                                argument=payload.get("argument"),
                                directory=payload.get("directory"),
                                prompt=payload.get("prompt"),
                                resume=payload.get("resume", False),
                                conversation_id=payload.get("conversation_id"),
                            )
                            await websocket.send_json(
                                {
                                    "type": "COMMAND_RESULT",
                                    "payload": {
                                        "req_id": payload.get("req_id"),
                                        "command": cmd,
                                        "result": res,
                                    },
                                }
                            )

                    elif cmd == "TERMINAL_EXEC":
                        if mrs.is_local_windows_host():
                            res = ms.execute_terminal_command(
                                command=payload.get("command", ""),
                                cwd=payload.get("working_dir"),
                                timeout=payload.get("timeout", 30),
                            )
                            await websocket.send_json(
                                {
                                    "type": "TERMINAL_RESULT",
                                    "payload": {
                                        "req_id": payload.get("req_id"),
                                        "result": res,
                                    },
                                }
                            )

                    elif cmd == "CAPTURE_SCREEN":
                        if mrs.is_local_windows_host():
                            res = ms.capture_windows_screen(max_width=payload.get("max_width", 1920))
                            await websocket.send_json(
                                {
                                    "type": "COMMAND_RESULT",
                                    "payload": {
                                        "req_id": payload.get("req_id"),
                                        "command": cmd,
                                        "result": res,
                                    },
                                }
                            )

                    elif cmd == "READ_FILE":
                        if mrs.is_local_windows_host():
                            res = ms.read_laptop_file(
                                file_path=payload.get("file_path", ""),
                                max_bytes=payload.get("max_bytes", 500000),
                            )
                            await websocket.send_json(
                                {
                                    "type": "COMMAND_RESULT",
                                    "payload": {
                                        "req_id": payload.get("req_id"),
                                        "command": cmd,
                                        "result": res,
                                    },
                                }
                            )

                    elif cmd == "LIST_FILES":
                        if mrs.is_local_windows_host():
                            res = ms.list_laptop_files(
                                directory=payload.get("directory"),
                                recursive=payload.get("recursive", False),
                                max_results=payload.get("max_results", 100),
                            )
                            await websocket.send_json(
                                {
                                    "type": "COMMAND_RESULT",
                                    "payload": {
                                        "req_id": payload.get("req_id"),
                                        "command": cmd,
                                        "result": res,
                                    },
                                }
                            )

                    elif cmd == "SEARCH_FILES":
                        if mrs.is_local_windows_host():
                            res = ms.search_laptop_files(
                                query=payload.get("query", ""),
                                directory=payload.get("directory"),
                                max_results=payload.get("max_results", 30),
                            )
                            await websocket.send_json(
                                {
                                    "type": "COMMAND_RESULT",
                                    "payload": {
                                        "req_id": payload.get("req_id"),
                                        "command": cmd,
                                        "result": res,
                                    },
                                }
                            )

                    elif cmd == "WRITE_FILE":
                        if mrs.is_local_windows_host():
                            res = ms.write_laptop_file(
                                file_path=payload.get("file_path", ""),
                                content=payload.get("content", ""),
                                mode=payload.get("mode", "overwrite"),
                            )
                            await websocket.send_json(
                                {
                                    "type": "COMMAND_RESULT",
                                    "payload": {
                                        "req_id": payload.get("req_id"),
                                        "command": cmd,
                                        "result": res,
                                    },
                                }
                            )

                    elif cmd in {"AGY_ATTACH_DIR", "AGY_SEND_INPUT", "AGY_SLASH_CMD", "AGY_GET_STATUS"}:
                        from app.services.agy_bridge import AgyError, agy_manager

                        try:
                            if cmd == "AGY_ATTACH_DIR":
                                session = agy_manager.spawn_or_attach(
                                    payload.get("directory"), payload.get("alias")
                                )
                                result = {"success": True, "session": session.to_dict()}
                            elif cmd == "AGY_SEND_INPUT":
                                key = payload.get("session_key") or agy_manager.current_session_key
                                text = payload.get("input", "")
                                if text.strip().startswith("/"):
                                    result = {"success": True, **agy_manager.send_raw_input(key, text)}
                                else:
                                    result = {"success": True, **agy_manager.send_prompt(key, text)}
                            elif cmd == "AGY_SLASH_CMD":
                                key = payload.get("session_key") or agy_manager.current_session_key
                                command = payload.get("command", "")
                                if not command.startswith("/"):
                                    command = f"/{command}"
                                result = {"success": True, **agy_manager.send_raw_input(key, command)}
                            else:
                                session = agy_manager.find_session(
                                    payload.get("session_key") or agy_manager.current_session_key
                                )
                                result = (
                                    {
                                        "success": True,
                                        "session": session.to_dict(),
                                        "recent_output": session.recent(120),
                                    }
                                    if session
                                    else {"success": False, "error": "No active Antigravity session."}
                                )
                        except AgyError as exc:
                            result = {"success": False, "error": str(exc)}
                        await websocket.send_json(
                            {
                                "type": "COMMAND_RESULT",
                                "payload": {
                                    "req_id": payload.get("req_id"),
                                    "command": cmd,
                                    "result": result,
                                },
                            }
                        )

                    # Forward command to target device (e.g. RING_PHONE)
                    msg = ms.MeshMessage(
                        type="REMOTE_COMMAND",
                        sender_device=device_id,
                        target_device=data.get("target_device"),
                        payload=payload,
                    )
                    await ms.hub.broadcast(msg, exclude_sender=True)

                elif msg_type == "HANDOFF":
                    ms.hub.set_handoff(
                        state_type=payload.get("type", "UNKNOWN"),
                        data=payload.get("data", {}),
                        sender_id=device_id,
                    )
                    msg = ms.MeshMessage(
                        type="HANDOFF",
                        sender_device=device_id,
                        payload=payload,
                    )
                    await ms.hub.broadcast(msg, exclude_sender=True)

                elif msg_type == "LAUNCH_APP":
                    if mrs.is_local_windows_host() and payload.get("target") != "mobile":
                        res = ms.launch_windows_app(
                            app_name=payload.get("app", "terminal"),
                            argument=payload.get("argument"),
                            directory=payload.get("directory"),
                            prompt=payload.get("prompt"),
                            resume=payload.get("resume", False),
                            conversation_id=payload.get("conversation_id"),
                        )
                        await websocket.send_json({
                            "type": "COMMAND_RESULT",
                            "payload": {"req_id": payload.get("req_id"), "command": "LAUNCH_APP", "result": res},
                        })
                    msg = ms.MeshMessage(type="LAUNCH_APP", sender_device=device_id, target_device=data.get("target_device"), payload=payload)
                    await ms.hub.broadcast(msg, exclude_sender=True)

                elif msg_type == "TERMINAL_EXEC":
                    if mrs.is_local_windows_host():
                        res = ms.execute_terminal_command(
                            command=payload.get("command", ""),
                            cwd=payload.get("working_dir"),
                            timeout=payload.get("timeout", 30),
                        )
                        await websocket.send_json({
                            "type": "TERMINAL_RESULT",
                            "payload": {"req_id": payload.get("req_id"), "result": res},
                        })
                    msg = ms.MeshMessage(type="TERMINAL_EXEC", sender_device=device_id, target_device=data.get("target_device"), payload=payload)
                    await ms.hub.broadcast(msg, exclude_sender=True)

                elif msg_type == "CAPTURE_SCREEN":
                    if mrs.is_local_windows_host():
                        res = ms.capture_windows_screen(max_width=payload.get("max_width", 1920))
                        await websocket.send_json({
                            "type": "COMMAND_RESULT",
                            "payload": {"req_id": payload.get("req_id"), "command": "CAPTURE_SCREEN", "result": res},
                        })
                    msg = ms.MeshMessage(type="CAPTURE_SCREEN", sender_device=device_id, target_device=data.get("target_device"), payload=payload)
                    await ms.hub.broadcast(msg, exclude_sender=True)

                elif msg_type == "PING":
                    if device_id in ms.hub.devices:
                        from datetime import UTC, datetime
                        ms.hub.devices[device_id].last_ping = datetime.now(UTC)

            except json.JSONDecodeError:
                continue

    except WebSocketDisconnect:
        ms.hub.disconnect(device_id)
        await ms.hub.broadcast_device_states()


COMPANION_HTML_PATH = Path(__file__).resolve().parent.parent.parent / "templates" / "mesh_companion.html"


@router.get("/companion", response_class=HTMLResponse)
def get_companion_page():
    """Serves the standalone Apple Continuity-style Mobile Companion web app."""
    candidate_paths = [
        Path(__file__).resolve().parent.parent.parent / "templates" / "mesh_companion.html",
        Path.cwd() / "backend" / "app" / "templates" / "mesh_companion.html",
        Path.cwd() / "app" / "templates" / "mesh_companion.html",
    ]
    for p in candidate_paths:
        if p.exists():
            return HTMLResponse(content=p.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>IRIS Mesh Companion template not found</h1>", status_code=404)


@router.get("/devices")
def list_connected_devices(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """List all currently connected mesh devices with battery and connection info."""
    devices = [d.model_dump(mode="json") for d in ms.hub.devices.values()]
    laptop_info = mrs.get_laptop_host_info(db, user.id)
    power = ms.get_windows_battery()
    if not power and laptop_info.get("battery_level") is not None:
        power = {
            "percent": laptop_info.get("battery_level"),
            "is_charging": laptop_info.get("is_charging") or False,
            "ac_status": "Plugged In" if laptop_info.get("is_charging") else "On Battery",
        }

    return {
        "devices": devices,
        "total_connected": len(devices),
        "host_power": power,
        "host_online": laptop_info.get("is_online", False),
        "laptop_host": laptop_info,
    }


@router.get("/clipboard")
def get_shared_clipboard():
    """Get the latest text synchronized on the Universal Clipboard."""
    return ms.hub.get_clipboard()


@router.post("/clipboard")
async def sync_shared_clipboard(
    req: ClipboardSyncRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Push text to Universal Clipboard, broadcasting locally and storing in cloud relay."""
    ms.hub.set_clipboard(req.text, sender_id=req.sender_device)
    msg = ms.MeshMessage(
        type="CLIPBOARD_SYNC",
        sender_device=req.sender_device,
        payload={"text": req.text},
    )
    await ms.hub.broadcast(msg, exclude_sender=True)
    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id=req.sender_device,
        target_device_id=None,
        msg_type="CLIPBOARD_SYNC",
        payload={"text": req.text},
    )
    return {"status": "synced", "length": len(req.text)}


@router.post("/files/upload")
async def upload_file_drop(
    file: UploadFile = File(...),
    sender_device: str = "web_client",
):
    """AirDrop equivalent: Upload a file to the File Vault to download on your other device."""
    safe_name = Path(file.filename or "file").name
    dest_path = ms.STORAGE_DIR / safe_name

    with open(dest_path, "wb") as f:
        content = await file.read()
        f.write(content)

    msg = ms.MeshMessage(
        type="FILE_DROP",
        sender_device=sender_device,
        payload={
            "filename": safe_name,
            "size": len(content),
            "download_url": f"/api/mesh/files/{safe_name}",
        },
    )
    await ms.hub.broadcast(msg, exclude_sender=True)
    return {
        "filename": safe_name,
        "size": len(content),
        "download_url": f"/api/mesh/files/{safe_name}",
    }


@router.get("/files")
def list_vault_files():
    """List all files currently stored in the Mesh File Vault."""
    files = []
    if ms.STORAGE_DIR.exists():
        for f in sorted(ms.STORAGE_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "url": f"/api/mesh/files/{f.name}",
                })
    return {"files": files, "count": len(files)}


@router.get("/files/{filename}")
def download_file_drop(filename: str):
    """Download a shared file from the File Vault."""
    file_path = ms.STORAGE_DIR / Path(filename).name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found in Mesh Vault.")
    return FileResponse(file_path, filename=file_path.name)


@router.get("/handoff")
def get_handoff_state():
    """Retrieve the latest active state to hand off (e.g. active focus session)."""
    return ms.hub.latest_handoff_state


@router.post("/handoff")
async def set_handoff_state(
    req: HandoffRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Hand off state to another surface (e.g. laptop to phone or phone to laptop)."""
    ms.hub.set_handoff(state_type=req.state_type, data=req.data, sender_id=req.sender_device)
    msg = ms.MeshMessage(
        type="HANDOFF",
        sender_device=req.sender_device,
        payload={"type": req.state_type, "data": req.data},
    )
    await ms.hub.broadcast(msg, exclude_sender=True)
    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id=req.sender_device,
        target_device_id=None,
        msg_type="HANDOFF",
        payload={"type": req.state_type, "data": req.data},
    )
    return {"status": "handed_off", "type": req.state_type}


@router.post("/command")
async def trigger_remote_command(
    req: RemoteCommandRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Trigger a remote hardware/OS command across devices."""
    if req.command == "LOCK_PC" and mrs.is_local_windows_host():
        pwd = req.parameters.get("password") or req.parameters.get("pin")
        mode = req.parameters.get("mode", "shield")
        locked = ms.lock_windows_pc(password=pwd, mode=mode)
        return {"command": "LOCK_PC", "executed": locked}

    if req.command == "UNLOCK_PC" and mrs.is_local_windows_host():
        pwd = req.parameters.get("password") or req.parameters.get("pin")
        unlocked = ms.unlock_windows_pc(password=pwd, pin=pwd)
        return {"command": "UNLOCK_PC", "executed": unlocked}

    if req.command in ["PING_LAPTOP", "PING_ALERT"] and mrs.is_local_windows_host():
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        return {"command": req.command, "executed": True}

    # Broadcast remote command locally and across cloud relay
    sender_id = str(req.parameters.get("sender_device") or "system")
    payload = {key: value for key, value in req.parameters.items() if key != "sender_device"}
    target = req.target_device or (
        mrs.LAPTOP_HOST_DEVICE_ID
        if req.command
        in [
            "LOCK_PC",
            "UNLOCK_PC",
            "PING_LAPTOP",
            "PING_ALERT",
            "LAUNCH_APP",
            "TRIGGER_CODER",
            "AGY_ATTACH_DIR",
            "AGY_SEND_INPUT",
            "AGY_SLASH_CMD",
            "AGY_GET_STATUS",
        ]
        else None
    )
    msg = ms.MeshMessage(
        type="REMOTE_COMMAND",
        sender_device=sender_id,
        target_device=target,
        payload={"command": req.command, **payload},
    )
    await ms.hub.broadcast(msg, exclude_sender=False)
    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id=sender_id,
        target_device_id=target,
        msg_type="REMOTE_COMMAND",
        payload={"command": req.command, **payload},
    )
    return {"command": req.command, "broadcast": True, "target": target or "all"}


# --- Terminal & Remote CLI Execution ---


class TerminalExecRequest(BaseModel):
    command: str = Field(..., description="PowerShell or shell command to execute on laptop")
    working_dir: str | None = Field(default=r"C:\kirtan\IRIS", description="Working directory")
    timeout: int = Field(default=30, ge=1, le=120, description="Execution timeout in seconds")


@router.post("/terminal/exec")
async def execute_laptop_terminal(
    req: TerminalExecRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Executes a terminal / PowerShell command on the Windows laptop remotely and returns output.

    If invoked directly on the local Windows workstation, executes immediately.
    If invoked via the Cloud Relay (e.g. phone on 5G), dispatches across the Sovereign Relay
    to the Windows laptop daemon and returns the laptop's actual execution output.
    """
    if mrs.is_local_windows_host():
        return ms.execute_terminal_command(
            command=req.command,
            cwd=req.working_dir,
            timeout=req.timeout,
        )

    # Dispatch across Sovereign Cloud Relay
    import secrets

    req_id = secrets.token_hex(6)
    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id="mobile_web_client",
        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
        msg_type="TERMINAL_EXEC",
        payload={
            "req_id": req_id,
            "command": req.command,
            "working_dir": req.working_dir,
            "timeout": req.timeout,
        },
    )

    # Wait for the laptop daemon to return the result
    res = await mrs.wait_for_relay_response(
        db=db,
        user_id=user.id,
        req_id=req_id,
        timeout_seconds=min(req.timeout + 4, 25.0),
    )
    if res is not None:
        return res

    return {
        "success": False,
        "returncode": 1,
        "stdout": "",
        "stderr": "Laptop did not respond within timeout. Make sure the IRIS backend is running on your Windows laptop.",
        "command": req.command,
        "cwd": req.working_dir or r"C:\kirtan\IRIS",
    }


@router.post("/terminal/open")
def open_laptop_terminal(
    argument: str | None = Query(None, description="Optional directory path"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Opens an interactive Windows Terminal / PowerShell window on the laptop desktop in user's home directory."""
    from pathlib import Path
    target_arg = argument or str(Path.home())
    if mrs.is_local_windows_host():
        return ms.launch_windows_app(app_name="terminal", argument=target_arg)

    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id="mobile_web_client",
        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
        msg_type="REMOTE_COMMAND",
        payload={"command": "LAUNCH_APP", "app": "terminal", "argument": target_arg},
    )
    return {"success": True, "message": "Dispatched terminal launch to laptop across Sovereign Relay."}


@router.post("/app/launch")
async def launch_remote_application(
    app: str = Query("antigravity", description="Application to launch (antigravity_cli, antigravity_ide, terminal, vscode, chrome, explorer)"),
    argument: str | None = Query(None, description="Optional path, URL, or argument"),
    directory: str | None = Query(None, description="Target directory or workspace path"),
    prompt: str | None = Query(None, description="Initial prompt for Antigravity CLI"),
    resume: bool = Query(False, description="Resume previous conversation for Antigravity CLI"),
    conversation_id: str | None = Query(None, description="Specific conversation ID for Antigravity CLI"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Launches or focuses a desktop application or interactive CLI on the Windows laptop."""
    if mrs.is_local_windows_host():
        return ms.launch_windows_app(
            app_name=app,
            argument=argument,
            directory=directory,
            prompt=prompt,
            resume=resume,
            conversation_id=conversation_id,
        )

    import secrets

    req_id = secrets.token_hex(6)
    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id="mobile_web_client",
        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
        msg_type="REMOTE_COMMAND",
        payload={
            "req_id": req_id,
            "command": "LAUNCH_APP",
            "app": app,
            "argument": argument,
            "directory": directory,
            "prompt": prompt,
            "resume": resume,
            "conversation_id": conversation_id,
        },
    )

    res = await mrs.wait_for_relay_response(
        db=db,
        user_id=user.id,
        req_id=req_id,
        timeout_seconds=6.0,
    )
    if res is not None:
        return res

    return {"success": True, "app": app, "message": f"Dispatched launch of {app} to laptop across Sovereign Relay."}


