"""FastAPI endpoints for IRIS Windows Computer Control and Desktop Automation."""

from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.computer.contracts import (
    ActionResult,
    ComputerAction,
    ComputerActionType,
    ComputerTaskRequest,
    ComputerTaskResult,
    SessionInfo,
    SessionState,
)
from app.computer.engine import computer_engine
from app.computer.native_ops import NativeOps
from app.computer.screen_perception import ScreenPerception
from app.computer.session import (
    KillSwitchTriggeredError,
    SessionSecurityError,
    get_secure_sentinel_dir,
    session_manager,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.execution_provider import is_serverless_runtime
from app.core.logging import get_logger
from app.models.mesh_pairing import MeshPairing
from app.models.user import User

logger = get_logger("iris.api.computer")

router = APIRouter(prefix="/computer", tags=["computer"])


def get_local_device_key() -> str:
    """Read or create the private local device key for sovereign machine authentication."""
    key_file = get_secure_sentinel_dir() / "device.key"
    if not key_file.exists():
        key = f"devk_{secrets.token_hex(32)}"
        try:
            key_file.write_text(key, encoding="utf-8")
            if os.name != "nt":
                key_file.chmod(0o600)
        except Exception:
            return key
        return key
    try:
        return key_file.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def verify_trusted_origin(request: Request) -> None:
    """Validate request Origin/Referer against allowed origins to prevent browser-based CSRF attacks."""
    origin = request.headers.get("origin")
    if origin:
        origin_clean = origin.rstrip("/")
        allowed = {"http://localhost:5173", "http://127.0.0.1:5173", "https://localhost", "capacitor://localhost"}
        for o in settings.cors_origins:
            allowed.add(o.rstrip("/"))
        is_allowed = (
            origin_clean in allowed
            or origin_clean.startswith("http://localhost:")
            or origin_clean.startswith("http://127.0.0.1:")
            or origin_clean.startswith("iris://")
        )
        if not is_allowed:
            logger.warning("Rejected computer control request from untrusted origin: %s", origin)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Untrusted origin '{origin}' is forbidden.",
            )


def require_device_or_companion_auth(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    x_auth_token: str | None = Header(default=None, alias="X-Computer-Auth-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """Authenticate device/companion access for session activation and kill-switch reset."""
    token = x_auth_token or x_device_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Missing device authentication token (X-Device-Token or X-Computer-Auth-Token).",
        )

    # 1. Match local machine key
    local_key = get_local_device_key()
    if local_key and secrets.compare_digest(token, local_key):
        return "local_device"

    # 2. Match companion secret
    if settings.iris_companion_secret and secrets.compare_digest(token, settings.iris_companion_secret):
        return "companion_secret"

    # 3. Match user's active mesh pairing token in database
    pairing = (
        db.query(MeshPairing)
        .filter(
            MeshPairing.user_id == user.id,
            MeshPairing.pairing_token == token,
            MeshPairing.is_active == True,
        )
        .first()
    )
    if pairing:
        return pairing.device_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication failed: Invalid or untrusted device token.",
    )


def require_active_session_token(
    x_computer_session_token: str | None = Header(default=None, alias="X-Computer-Session-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """Enforce mandatory session token authentication on all privileged computer control endpoints."""
    token = x_computer_session_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Mandatory 'X-Computer-Session-Token' header is missing.",
        )

    valid, err_msg = session_manager.verify_session_token_detailed(token)
    if not valid:
        if session_manager.is_kill_switch_engaged:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=err_msg or "Emergency kill-switch is engaged.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err_msg or "Invalid, expired, or revoked computer session token.",
        )
    return token


# --- Request/Response Schemas ---


class ActivateSessionRequest(BaseModel):
    reason: str = Field(..., description="Purpose or task description for desktop control session")
    expiry_minutes: int | None = Field(default=5, ge=1, le=60, description="Session TTL in minutes")
    device_id: str | None = Field(default=None, description="Optional caller device ID")


class SessionStopRequest(BaseModel):
    reason: str | None = Field(default="User stopped session", description="Reason for stopping session")


class KillSwitchRequest(BaseModel):
    source: str = Field(default="user_ui", description="Source of the emergency kill switch activation")


class ScreenshotRequest(BaseModel):
    window: str | None = Field(default=None, description="Window title or substring to capture, or None for full screen")
    max_width: int = Field(default=1920, ge=320, le=3840)
    quality: int = Field(default=85, ge=10, le=100)


class ComputerStatusResponse(BaseModel):
    session: SessionInfo
    is_windows: bool
    is_serverless: bool
    interactive_available: bool
    companion_online: bool
    message: str


# --- Endpoints ---


@router.get("/status", response_model=ComputerStatusResponse)
def get_computer_status(
    _user: User = Depends(current_user),
) -> ComputerStatusResponse:
    """Get real-time state of the computer-control subsystem, active sessions, and hardware availability."""
    session_info = session_manager.get_info(include_token=False)
    is_win = os.name == "nt"
    serverless = is_serverless_runtime()
    interactive_available = is_win and not serverless

    # Check if a companion desktop device is connected via mesh
    companion_online = interactive_available
    if not companion_online:
        from app.services.mesh_service import hub
        for dev in hub.devices.values():
            if dev.device_type == "laptop_windows":
                companion_online = True
                break

    msg = "Computer control is ready."
    if session_info.kill_switch_engaged:
        msg = f"EMERGENCY KILL SWITCH ENGAGED ({session_info.kill_switch_source}). All actions blocked."
    elif session_info.state == SessionState.ACTIVE:
        msg = f"Active session: {session_info.session_id} (Reason: {session_info.reason})"
    elif not companion_online and serverless:
        msg = "Local Windows companion is offline. Connect the IRIS desktop companion to enable computer control."

    return ComputerStatusResponse(
        session=session_info,
        is_windows=is_win,
        is_serverless=serverless,
        interactive_available=interactive_available,
        companion_online=companion_online,
        message=msg,
    )


@router.post("/session/start", response_model=SessionInfo)
def start_session(
    body: ActivateSessionRequest,
    user: User = Depends(current_user),
    device_id: str = Depends(require_device_or_companion_auth),
    _origin: None = Depends(verify_trusted_origin),
) -> SessionInfo:
    """Explicitly activate a computer-control session upon verified device authorization."""
    try:
        session = session_manager.activate_session(
            reason=body.reason,
            expiry_minutes=body.expiry_minutes,
            authorized_by=user.email or "authorized_user",
            device_id=body.device_id or device_id,
        )
        return session
    except KillSwitchTriggeredError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to activate session: {exc}",
        ) from exc


@router.post("/session/stop", response_model=SessionInfo)
def stop_session(
    body: SessionStopRequest,
    _token: str = Depends(require_active_session_token),
    _origin: None = Depends(verify_trusted_origin),
) -> SessionInfo:
    """Terminate the active session and return to background idle mode."""
    return session_manager.terminate_session(reason=body.reason or "User terminated session")


@router.post("/session/pause", response_model=SessionInfo)
def pause_session(
    _token: str = Depends(require_active_session_token),
    _origin: None = Depends(verify_trusted_origin),
) -> SessionInfo:
    """Temporarily pause active computer control execution."""
    return session_manager.pause_session("Paused by user")


@router.post("/session/resume", response_model=SessionInfo)
def resume_session(
    _token: str = Depends(require_active_session_token),
    _origin: None = Depends(verify_trusted_origin),
) -> SessionInfo:
    """Resume a paused computer control session."""
    try:
        return session_manager.resume_session()
    except KillSwitchTriggeredError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(exc),
        ) from exc


@router.post("/kill-switch", response_model=SessionInfo)
def trigger_kill_switch(
    body: KillSwitchRequest,
    _user: User = Depends(current_user),
) -> SessionInfo:
    """Emergency immediate kill-switch: terminates all active operations and revokes desktop access.
    
    Universally accessible without token or origin restriction to ensure emergency responsiveness.
    """
    session_manager.trigger_kill_switch(source=body.source)
    return session_manager.get_info()


@router.post("/kill-switch/reset", response_model=SessionInfo)
def reset_kill_switch(
    _device_id: str = Depends(require_device_or_companion_auth),
    _origin: None = Depends(verify_trusted_origin),
) -> SessionInfo:
    """Reset the emergency kill switch and return subsystem to background mode."""
    return session_manager.reset_kill_switch()


@router.post("/action", response_model=ActionResult)
def execute_single_action(
    action: ComputerAction,
    _user: User = Depends(current_user),
    _origin: None = Depends(verify_trusted_origin),
    _token: str = Depends(require_active_session_token),
) -> ActionResult:
    """Execute a single atomic computer-control primitive within active session boundaries."""
    try:
        return computer_engine.execute_action(action)
    except KillSwitchTriggeredError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(exc),
        ) from exc
    except SessionSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error executing computer action: %s", exc)
        return ActionResult(
            action_type=action.action_type.value,
            success=False,
            error=str(exc),
        )


@router.post("/execute-task", response_model=ComputerTaskResult)
def execute_task(
    req: ComputerTaskRequest,
    _user: User = Depends(current_user),
    _origin: None = Depends(verify_trusted_origin),
    _token: str = Depends(require_active_session_token),
) -> ComputerTaskResult:
    """Execute a high-level natural language computer automation task (observe -> plan -> act -> verify)."""
    try:
        return computer_engine.execute_task(req)
    except KillSwitchTriggeredError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(exc),
        ) from exc
    except SessionSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error executing computer task: %s", exc)
        return ComputerTaskResult(
            task_id=req.task_id,
            session_id=None,
            status="failed",
            summary=f"Task execution failed: {exc}",
            verified=False,
        )


@router.get("/windows")
def list_desktop_windows(
    visible_only: bool = Query(default=True),
    _user: User = Depends(current_user),
    _origin: None = Depends(verify_trusted_origin),
    _token: str = Depends(require_active_session_token),
) -> list[dict[str, Any]]:
    """List open application windows on the desktop (requires active session)."""
    try:
        session_manager.validate_action_allowed(ComputerActionType.WINDOW_LIST)
    except KillSwitchTriggeredError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(exc),
        ) from exc
    except SessionSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return NativeOps.list_windows(visible_only=visible_only)


@router.post("/screenshot")
def take_screenshot(
    req: ScreenshotRequest,
    _user: User = Depends(current_user),
    _origin: None = Depends(verify_trusted_origin),
    _token: str = Depends(require_active_session_token),
) -> dict[str, Any]:
    """Capture a screenshot of the desktop or a specific window."""
    info = session_manager.get_info()
    if info.kill_switch_engaged:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Emergency kill-switch is engaged.",
        )
    if info.state != SessionState.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Screen observation is disabled in background mode. Activate a computer-control session first.",
        )

    if req.window:
        return ScreenPerception.capture_window_screenshot(req.window, quality=req.quality)
    return ScreenPerception.capture_screenshot(max_width=req.max_width, quality=req.quality)
    """Capture a screenshot of the desktop or a specific window."""
    info = session_manager.get_info()
    if info.kill_switch_engaged:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Emergency kill-switch is engaged.",
        )
    if info.state != SessionState.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Screen observation is disabled in background mode. Activate a computer-control session first.",
        )

    if req.window:
        return ScreenPerception.capture_window_screenshot(req.window, quality=req.quality)
    return ScreenPerception.capture_screenshot(max_width=req.max_width, quality=req.quality)
