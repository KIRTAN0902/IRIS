"""FastAPI routes and WebSocket gateway for IRIS Mesh (Cross-Device Continuity)."""

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
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.models.user import User
from app.services import mesh_service as ms

router = APIRouter(prefix="/mesh", tags=["mesh"])


class ClipboardSyncRequest(BaseModel):
    text: str = Field(..., description="Text content to sync across devices")
    sender_device: str = "web_client"


class RemoteCommandRequest(BaseModel):
    command: str = Field(..., description="'LOCK_PC', 'RING_PHONE', 'GET_BATTERY'")
    target_device: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class HandoffRequest(BaseModel):
    state_type: str = Field(..., description="'FOCUS_SESSION', 'READING_TAB', 'TASK'")
    data: dict[str, Any] = Field(..., description="State payload to hand off")
    sender_device: str = "web_client"


@router.websocket("/ws")
async def mesh_websocket_endpoint(
    websocket: WebSocket,
    device_id: str = Query(..., description="Unique client ID (e.g. 'phone_mobile_1')"),
    device_type: str = Query("phone_mobile", description="'laptop_windows' or 'phone_mobile'"),
    name: str = Query("Mobile Phone", description="Friendly device name"),
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
    if COMPANION_HTML_PATH.exists():
        return HTMLResponse(content=COMPANION_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>IRIS Mesh Companion template not found</h1>", status_code=404)


@router.get("/devices")
def list_connected_devices():
    """List all currently connected mesh devices with battery and connection info."""
    devices = [d.model_dump(mode="json") for d in ms.hub.devices.values()]
    # Inject Windows host power info if on laptop
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
async def sync_shared_clipboard(req: ClipboardSyncRequest):
    """Push text to Universal Clipboard and broadcast to all connected devices."""
    ms.hub.set_clipboard(req.text, sender_id=req.sender_device)
    msg = ms.MeshMessage(
        type="CLIPBOARD_SYNC",
        sender_device=req.sender_device,
        payload={"text": req.text},
    )
    await ms.hub.broadcast(msg, exclude_sender=True)
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
async def set_handoff_state(req: HandoffRequest):
    """Hand off state to another surface (e.g. laptop to phone or phone to laptop)."""
    ms.hub.set_handoff(state_type=req.state_type, data=req.data, sender_id=req.sender_device)
    msg = ms.MeshMessage(
        type="HANDOFF",
        sender_device=req.sender_device,
        payload={"type": req.state_type, "data": req.data},
    )
    await ms.hub.broadcast(msg, exclude_sender=True)
    return {"status": "handed_off", "type": req.state_type}


@router.post("/command")
async def trigger_remote_command(req: RemoteCommandRequest):
    """Trigger a remote hardware/OS command across devices."""
    if req.command == "LOCK_PC":
        locked = ms.lock_windows_pc()
        return {"command": "LOCK_PC", "executed": locked}

    # Broadcast remote command (e.g. RING_PHONE)
    msg = ms.MeshMessage(
        type="REMOTE_COMMAND",
        sender_device="system",
        target_device=req.target_device,
        payload={"command": req.command, **req.parameters},
    )
    await ms.hub.broadcast(msg, exclude_sender=False)
    return {"command": req.command, "broadcast": True, "target": req.target_device or "all"}
