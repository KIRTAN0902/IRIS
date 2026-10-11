"""FastAPI routes, WebSocket gateway, Sovereign Relay, and Screen Mirroring for IRIS Mesh."""

from __future__ import annotations

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


class PairingVerifyRequest(BaseModel):
    code: str = Field(..., description="6-digit pairing code or QR token")
    device_id: str = Field(..., description="Unique client-assigned ID")
    device_name: str = "Mobile Companion"
    device_type: str = "phone_mobile"


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
    """Generates a secure 6-digit numeric PIN code & QR code for one-time pairing."""
    invite = mrs.generate_pairing_invite(
        db=db,
        user_id=user.id,
        device_name=req.device_name,
        expires_minutes=15,
    )
    return invite


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
    """Lists all active paired sovereign mesh devices."""
    devices = mrs.list_paired_devices(db=db, user_id=user.id)
    return {
        "paired_devices": [
            {
                "id": d.id,
                "device_id": d.device_id,
                "device_name": d.device_name,
                "device_type": d.device_type,
                "battery_level": d.battery_level,
                "is_charging": d.is_charging,
                "paired_at": d.paired_at.isoformat() if d.paired_at else None,
                "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            }
            for d in devices
        ],
        "count": len(devices),
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
                        ms.lock_windows_pc()
                    elif cmd == "DEVICE_BATTERY":
                        if device_id in ms.hub.devices:
                            ms.hub.devices[device_id].battery_level = payload.get("battery_level")
                            ms.hub.devices[device_id].is_charging = payload.get("is_charging")
                            await ms.hub.broadcast_device_states()

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
def list_connected_devices():
    """List all currently connected mesh devices with battery and connection info."""
    devices = [d.model_dump(mode="json") for d in ms.hub.devices.values()]
    windows_battery = ms.get_windows_battery()
    return {
        "devices": devices,
        "total_connected": len(devices),
        "host_power": windows_battery,
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
    if req.command == "LOCK_PC":
        locked = ms.lock_windows_pc()
        return {"command": "LOCK_PC", "executed": locked}

    # Broadcast remote command locally and across cloud relay
    msg = ms.MeshMessage(
        type="REMOTE_COMMAND",
        sender_device="system",
        target_device=req.target_device,
        payload={"command": req.command, **req.parameters},
    )
    await ms.hub.broadcast(msg, exclude_sender=False)
    mrs.push_relay_message(
        db=db,
        user_id=user.id,
        sender_device_id="system",
        target_device_id=req.target_device,
        msg_type="REMOTE_COMMAND",
        payload={"command": req.command, **req.parameters},
    )
    return {"command": req.command, "broadcast": True, "target": req.target_device or "all"}
