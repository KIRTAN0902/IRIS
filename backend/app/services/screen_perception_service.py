"""IRIS Screen Perception Service: Unified cross-device visual intelligence.

Coordinates:
1. Target device resolution (Windows Workstation vs Android Companion).
2. Hardware screen capture (Win32/GDI on Windows, PixelCopy/MediaProjection on Android).
3. Ephemeral vision processing via VisionService (Zero-Image-Storage guarantee).
4. Visual context lifecycle, memory attachment, and freshness management.
5. Grounded visual question answering and change detection.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.devices.contracts import DeviceType
from app.devices.registry import default_registry
from app.devices.target_resolver import default_target_resolver
from app.models.user import User
from app.services.vision_service import VisionExtractionResult, vision_service

logger = logging.getLogger("iris.services.screen_perception")


@dataclass
class ActiveVisualPerception:
    """In-memory cache of the most recent visual perception for a user."""

    timestamp: float
    device_type: DeviceType
    summary: str
    extracted_text_or_code: str
    actionable_items: list[dict[str, Any]] = field(default_factory=list)
    detected_domain: str = "OPERATOR"
    dimensions: tuple[int, int] = (1920, 1080)
    capture_id: str = ""

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    def is_fresh(self, max_age_seconds: float = 120.0) -> bool:
        return self.age_seconds <= max_age_seconds


class ScreenPerceptionService:
    """Manages cross-device visual perception, capture coordination, and conversational context."""

    _instance: ScreenPerceptionService | None = None

    def __new__(cls) -> ScreenPerceptionService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._active_perceptions = {}
            cls._pending_captures = {}
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_active_perceptions"):
            self._active_perceptions: dict[int, ActiveVisualPerception] = {}
            self._pending_captures: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def get_active_perception(
        self, user_id: int, max_age_seconds: float = 120.0
    ) -> ActiveVisualPerception | None:
        """Retrieves active visual perception if fresh, or None if expired."""
        perception = self._active_perceptions.get(user_id)
        if perception and perception.is_fresh(max_age_seconds):
            return perception
        return None

    def get_stale_perception(self, user_id: int) -> ActiveVisualPerception | None:
        """Returns the last perception regardless of age to detect stale context."""
        return self._active_perceptions.get(user_id)

    def clear_active_perception(self, user_id: int) -> None:
        self._active_perceptions.pop(user_id, None)

    def register_capture_future(self, request_id: str, future: asyncio.Future[dict[str, Any]]) -> None:
        self._pending_captures[request_id] = future

    def complete_capture_future(self, request_id_or_payload: Any, payload: dict[str, Any] | None = None) -> bool:
        if isinstance(request_id_or_payload, dict):
            req_id = request_id_or_payload.get("request_id")
            actual_payload = request_id_or_payload
        elif isinstance(request_id_or_payload, str) and payload is not None:
            req_id = request_id_or_payload
            actual_payload = payload
        elif isinstance(request_id_or_payload, str) and payload is None:
            # Called with just base64 string
            req_id = None
            actual_payload = {"image_base64": request_id_or_payload}
        else:
            req_id = None
            actual_payload = {}

        if req_id and req_id in self._pending_captures:
            fut = self._pending_captures.pop(req_id)
            if not fut.done():
                fut.set_result(actual_payload)
                return True
        elif self._pending_captures:
            first_key = next(iter(self._pending_captures))
            fut = self._pending_captures.pop(first_key)
            if not fut.done():
                fut.set_result(actual_payload)
                return True
        return False

    async def capture_and_analyze(
        self,
        *,
        db: Session,
        user: User,
        target_device_hint: str | None = None,
        question: str = "",
        client_ws: Any | None = None,
        timeout_seconds: float = 15.0,
    ) -> tuple[bool, str, VisionExtractionResult | None]:
        """Captures the screen of the intended target device, analyzes it, and updates conversational context."""
        # 1. Resolve Target Device
        resolved_device = self._resolve_target_device(target_device_hint, client_ws)

        # 2. Capture Screen Hardware Buffer
        capture_success, raw_bytes, mime, width, height, err_msg = await self._perform_capture(
            device_type=resolved_device,
            db=db,
            user=user,
            client_ws=client_ws,
            timeout_seconds=timeout_seconds,
        )

        if not capture_success or not raw_bytes:
            error_reason = err_msg or "Screen capture could not be obtained."
            logger.warning("Screen capture failed on %s: %s", resolved_device.value, error_reason)
            return False, error_reason, None

        # 3. Analyze Ephemeral Image via VisionService (Zero Image Storage Guarantee)
        user_prompt = question.strip() or "Describe what is currently visible on the screen, active windows, code, errors, or forms in detail."
        try:
            vision_result = await vision_service.analyze_ephemeral_images(
                images=[(raw_bytes, mime)],
                user_prompt=user_prompt,
            )
        except Exception as exc:
            logger.error("Vision analysis failed for screen capture: %s", exc, exc_info=True)
            return False, f"Vision analysis failed: {exc}", None

        # 4. Attach Visual Context to Persistent Situational Memory
        try:
            vision_service.store_visual_context(db, user, vision_result)
        except Exception as exc:
            logger.warning("Could not persist visual memory record: %s", exc)

        # 5. Update Active Visual Perception Cache for Immediate Follow-up Queries
        import secrets
        cap_id = f"cap_{secrets.token_hex(6)}"
        active = ActiveVisualPerception(
            timestamp=time.time(),
            device_type=resolved_device,
            summary=vision_result.summary,
            extracted_text_or_code=vision_result.extracted_text_or_code,
            actionable_items=vision_result.actionable_items,
            detected_domain=vision_result.detected_domain,
            dimensions=(width, height),
            capture_id=cap_id,
        )
        self._active_perceptions[user.id] = active
        logger.info(
            "Screen perception updated for user %s on %s (capture %s): %s",
            user.id,
            resolved_device.value,
            cap_id,
            vision_result.summary[:100],
        )

        return True, vision_result.summary, vision_result

    def format_perception_context_for_prompt(
        self, user_id: int, max_age_seconds: float = 120.0
    ) -> str | None:
        """Formats the active visual perception block for injection into Supervisor / Agent reasoning context."""
        active = self.get_active_perception(user_id, max_age_seconds)
        if not active:
            return None

        dev_label = "Windows Laptop" if active.device_type == DeviceType.WINDOWS_LAPTOP else "Android Phone"
        elapsed = int(active.age_seconds)
        lines = [
            f"[📷 ACTIVE VISUAL CONTEXT ({dev_label}, Captured {elapsed}s ago)]:",
            f"Screen Summary: {active.summary}",
        ]
        if active.extracted_text_or_code:
            lines.append("Visible Text / UI Elements / Code:")
            lines.append(active.extracted_text_or_code[:2500])
        if active.actionable_items:
            actions_str = ", ".join(
                str(a.get("title") or a.get("details") or a.get("merchant") or "")
                for a in active.actionable_items
                if a.get("title") or a.get("details")
            )
            if actions_str:
                lines.append(f"Detected UI Actionables: {actions_str}")

        return "\n".join(lines)

    async def answer_visual_followup(
        self,
        question: str,
        db: Session,
        user: User,
        client_ws: Any | None = None,
    ) -> str:
        """Answers follow-up questions referencing the screen with visual grounding and change detection."""
        active = self.get_active_perception(user.id, max_age_seconds=120.0)

        # Change Detection: If previous capture is older than 120s, flag as stale
        if not active:
            stale = self.get_stale_perception(user.id)
            if stale:
                stale_min = int(stale.age_seconds // 60)
                return (
                    f"My previous view of your screen is {stale_min} minute(s) old and may have changed. "
                    "Please ask me to inspect your screen again so I can give you an accurate, up-to-date answer."
                )
            return "I don't have an active view of your screen. Please ask me 'What is on my screen?' first so I can inspect it."

        # Ground response in visual evidence
        from app.agent.supervisor import IrisSupervisor
        context_block = self.format_perception_context_for_prompt(user.id) or ""
        grounded_query = f"{context_block}\n\nUser Question regarding this screen:\n{question}\nAnswer directly, accurately, and concisely based strictly on the visible elements above. If asked which button to click or what action to take, specify the exact element without pretending to have clicked it."

        res_schema, _ = await IrisSupervisor.process(
            db=db,
            user=user,
            user_message=grounded_query,
        )
        return res_schema.message

    def _resolve_target_device(
        self, hint: str | None, client_ws: Any | None
    ) -> DeviceType:
        if hint:
            low = hint.lower()
            if any(k in low for k in ["phone", "mobile", "android", "realme"]):
                return DeviceType.ANDROID_PHONE
            if any(k in low for k in ["laptop", "pc", "workstation", "computer", "windows"]):
                return DeviceType.WINDOWS_LAPTOP

        # If hint is absent, infer from client websocket or presence
        if client_ws:
            # If client_ws client headers or type indicate phone, return phone
            ws_type = getattr(client_ws, "device_type", None)
            if ws_type == "phone":
                return DeviceType.ANDROID_PHONE

        # Default to Windows Workstation if running local host
        try:
            from app.services import mesh_relay_service as mrs
            if mrs.is_local_windows_host():
                return DeviceType.WINDOWS_LAPTOP
        except Exception:
            pass

        return DeviceType.WINDOWS_LAPTOP

    async def _perform_capture(
        self,
        device_type: DeviceType,
        db: Session,
        user: User,
        client_ws: Any | None,
        timeout_seconds: float,
    ) -> tuple[bool, bytes | None, str, int, int, str | None]:
        """Performs real hardware capture across Windows or Android."""
        # --- Platform A: Windows Workstation ---
        if device_type == DeviceType.WINDOWS_LAPTOP:
            from app.services import mesh_relay_service as mrs
            from app.services import mesh_service as ms

            if mrs.is_local_windows_host():
                cap_res = ms.capture_windows_screen(max_width=1920)
                if not cap_res.get("success"):
                    return False, None, "", 0, 0, cap_res.get("error", "Windows screen capture failed.")
                b64 = cap_res.get("image_base64", "")
                raw = base64.b64decode(b64)
                w = cap_res.get("width", 1920)
                h = cap_res.get("height", 1080)
                return True, raw, "image/jpeg", w, h, None
            else:
                # Capture via relay if remote
                if not mrs.is_host_laptop_online(db, user.id, threshold_seconds=300.0):
                    return False, None, "", 0, 0, "Windows laptop is currently offline on Sovereign Mesh."
                import secrets
                req_id = secrets.token_hex(6)
                mrs.push_relay_message(
                    db=db,
                    user_id=user.id,
                    sender_device_id="screen_perception",
                    target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                    msg_type="REMOTE_COMMAND",
                    payload={"command": "CAPTURE_SCREEN", "max_width": 1920, "req_id": req_id},
                )
                res = await mrs.wait_for_relay_response(
                    db=db,
                    user_id=user.id,
                    req_id=req_id,
                    timeout_seconds=timeout_seconds,
                )
                if not res or not res.get("success"):
                    return False, None, "", 0, 0, (res.get("error") if res else "Laptop screen capture timed out.")
                b64 = res.get("image_base64", "")
                raw = base64.b64decode(b64)
                w = res.get("width", 1920)
                h = res.get("height", 1080)
                return True, raw, "image/jpeg", w, h, None

        # --- Platform B: Android Companion ---
        if device_type == DeviceType.ANDROID_PHONE:
            # Check if phone is online
            if not default_registry.is_device_online(DeviceType.ANDROID_PHONE, db=db, user_id=str(user.id)):
                return False, None, "", 0, 0, "Android phone (Realme GT 7T) is currently offline or unreachable on Sovereign Mesh."

            # If client_ws is available (connected voice/mesh websocket)
            if client_ws:
                import secrets
                req_id = f"cap_req_{secrets.token_hex(4)}"
                loop = asyncio.get_running_loop()
                fut: asyncio.Future[dict[str, Any]] = loop.create_future()
                self.register_capture_future(req_id, fut)

                try:
                    await client_ws.send_json({
                        "type": "request_screen_capture",
                        "request_id": req_id,
                    })
                    response_payload = await asyncio.wait_for(fut, timeout=timeout_seconds)
                    b64 = response_payload.get("image_base64", "")
                    if not b64 or response_payload.get("error"):
                        err = response_payload.get("error") or "Screen capture permission was denied or cancelled."
                        return False, None, "", 0, 0, err

                    # Strip data URI header if present
                    if b64.startswith("data:"):
                        _, _, b64 = b64.partition(",")

                    raw = base64.b64decode(b64)
                    return True, raw, "image/jpeg", 1080, 2400, None
                except asyncio.TimeoutError:
                    return False, None, "", 0, 0, "Mobile screen capture request timed out."
                finally:
                    self._pending_captures.pop(req_id, None)

            # Fallback: relay capture if phone paired
            return False, None, "", 0, 0, "No active companion WebSocket connection available to receive screen capture."

        return False, None, "", 0, 0, f"Unsupported device type: {device_type}"


# Global Screen Perception singleton
screen_perception_service = ScreenPerceptionService()
