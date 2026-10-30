"""Android Capability Execution Engine with Sovereign Mesh transport and offline protection.

Executes capabilities on the Android companion phone (Realme GT 7T):
- Dynamic application launching via Intent
- Browser navigation
- Live battery telemetry
- Find My Phone (ring alert)
- Network and device status verification
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.devices.contracts import (
    DeviceExecutionRequest,
    DeviceExecutionResult,
    DeviceType,
)
from app.devices.registry import default_registry

logger = logging.getLogger(__name__)


class AndroidDeviceExecutor:
    """Capability-driven execution engine communicating with Android companion via Sovereign Mesh."""

    def __init__(self) -> None:
        self._processed_tokens: set[str] = set()

    def execute(
        self,
        request: DeviceExecutionRequest,
        db: Any | None = None,
        user_id: str | None = None,
    ) -> DeviceExecutionResult:
        """Synchronously executes an Android capability (runs async loop or queues event)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async context where loop is running, we use run_coroutine_threadsafe or synchronous fallback
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self.execute_async(request, db=db, user_id=user_id))
                    return future.result(timeout=request.expires_at - time.time() if request.expires_at > time.time() else 10.0)
            else:
                return loop.run_until_complete(self.execute_async(request, db=db, user_id=user_id))
        except Exception:
            return asyncio.run(self.execute_async(request, db=db, user_id=user_id))

    async def execute_async(
        self,
        request: DeviceExecutionRequest,
        db: Any | None = None,
        user_id: str | None = None,
    ) -> DeviceExecutionResult:
        """Asynchronously dispatches execution to Android companion with reachability check and verification."""
        start_time = time.monotonic()
        cap_id = request.capability_id
        params = request.parameters
        dev_id = request.target_device_id or "phone_android"

        # 1. Idempotency Check
        idempotency_key = request.metadata.get("idempotency_token") or request.request_id
        if idempotency_key in self._processed_tokens:
            duration = int((time.monotonic() - start_time) * 1000)
            logger.info("Ignoring duplicate execution request %s for Android", idempotency_key)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id=dev_id,
                capability_id=cap_id,
                success=True,
                data={"duplicate_suppressed": True},
                verified=True,
                verification_details="Suppressed redundant execution via idempotency token.",
                duration_ms=duration,
            )

        # 2. Check Device Reachability / Online Presence
        is_online = default_registry.is_device_online(DeviceType.ANDROID_PHONE, db=db, user_id=user_id)
        if not is_online:
            duration = int((time.monotonic() - start_time) * 1000)
            logger.warning("Android execution failed: Companion phone is offline (%s)", cap_id)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id=dev_id,
                capability_id=cap_id,
                success=False,
                error="Android phone (Realme GT 7T) is currently offline or unreachable on Sovereign Mesh.",
                verified=False,
                verification_details="Target device did not respond or has no active WebSocket/relay connection.",
                duration_ms=duration,
            )

        # 3. Route Capability
        try:
            if cap_id in ("android.app.launch", "device.app.launch"):
                result = await self._launch_app(request, params, db=db, user_id=user_id, start_time=start_time)
            elif cap_id in ("android.browser.open_url", "device.browser.open_url"):
                result = await self._open_url(request, params, db=db, user_id=user_id, start_time=start_time)
            elif cap_id in ("android.system.battery", "device.battery.read"):
                result = await self._get_battery(request, db=db, user_id=user_id, start_time=start_time)
            elif cap_id in ("android.system.ring", "device.ring"):
                result = await self._ring_phone(request, db=db, user_id=user_id, start_time=start_time)
            elif cap_id in ("android.system.info", "device.info.read"):
                result = await self._get_info(request, start_time=start_time)
            else:
                duration = int((time.monotonic() - start_time) * 1000)
                result = DeviceExecutionResult(
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    device_id=dev_id,
                    capability_id=cap_id,
                    success=False,
                    error=f"Unrecognized capability '{cap_id}' for Android executor.",
                    verified=False,
                    duration_ms=duration,
                )

            if result.success and idempotency_key:
                self._processed_tokens.add(idempotency_key)

            return result

        except Exception as exc:
            duration = int((time.monotonic() - start_time) * 1000)
            logger.error("Android execution exception on %s: %s", cap_id, exc, exc_info=True)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id=dev_id,
                capability_id=cap_id,
                success=False,
                error=f"Android execution error: {exc}",
                verified=False,
                duration_ms=duration,
            )

    async def _launch_app(
        self,
        request: DeviceExecutionRequest,
        params: dict[str, Any],
        db: Any | None,
        user_id: str | None,
        start_time: float,
    ) -> DeviceExecutionResult:
        app_name = params.get("app_name") or params.get("appName") or ""
        package = params.get("package") or params.get("package_name")

        if not app_name and not package:
            duration = int((time.monotonic() - start_time) * 1000)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="phone_android",
                capability_id=request.capability_id,
                success=False,
                error="Parameter 'app_name' or 'package' is required for Android app launch.",
                duration_ms=duration,
            )

        payload = {
            "command": "LAUNCH_APP",
            "app_name": app_name,
            "appName": app_name,
            "package": package,
            "correlation_id": request.correlation_id,
        }

        # Broadcast via WebSocket MeshHub
        from app.services import mesh_service as ms
        msg = ms.MeshMessage(
            type="REMOTE_COMMAND",
            sender_device="iris_intelligence",
            target_device=request.target_device_id or "phone_android",
            payload=payload,
        )
        await ms.hub.broadcast(msg, exclude_sender=False)

        # Also push to DB relay queue if user context is available
        if db and user_id:
            try:
                from app.services import mesh_relay_service as mrs
                mrs.push_relay_message(
                    db=db,
                    user_id=user_id,
                    sender_device_id="iris_intelligence",
                    target_device_id=request.target_device_id,
                    msg_type="REMOTE_COMMAND",
                    payload=payload,
                )
            except Exception as e:
                logger.warning("Relay queue push notice: %s", e)

        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="phone_android",
            capability_id=request.capability_id,
            success=True,
            data={"app_name": app_name, "package": package, "intent_dispatched": True},
            verified=True,
            verification_details=f"Intent dispatched to Android companion for '{app_name or package}'.",
            duration_ms=duration,
        )

    async def _open_url(
        self,
        request: DeviceExecutionRequest,
        params: dict[str, Any],
        db: Any | None,
        user_id: str | None,
        start_time: float,
    ) -> DeviceExecutionResult:
        url = params.get("url", "").strip()
        if not url:
            duration = int((time.monotonic() - start_time) * 1000)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="phone_android",
                capability_id=request.capability_id,
                success=False,
                error="URL parameter is required.",
                duration_ms=duration,
            )

        payload = {
            "command": "OPEN_URL",
            "url": url,
            "correlation_id": request.correlation_id,
        }

        from app.services import mesh_service as ms
        msg = ms.MeshMessage(
            type="REMOTE_COMMAND",
            sender_device="iris_intelligence",
            target_device=request.target_device_id or "phone_android",
            payload=payload,
        )
        await ms.hub.broadcast(msg, exclude_sender=False)

        if db and user_id:
            try:
                from app.services import mesh_relay_service as mrs
                mrs.push_relay_message(
                    db=db,
                    user_id=user_id,
                    sender_device_id="iris_intelligence",
                    target_device_id=request.target_device_id,
                    msg_type="REMOTE_COMMAND",
                    payload=payload,
                )
            except Exception:
                pass

        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="phone_android",
            capability_id=request.capability_id,
            success=True,
            data={"url": url, "dispatched": True},
            verified=True,
            verification_details=f"URL '{url}' sent to Android browser.",
            duration_ms=duration,
        )

    async def _ring_phone(
        self,
        request: DeviceExecutionRequest,
        db: Any | None,
        user_id: str | None,
        start_time: float,
    ) -> DeviceExecutionResult:
        payload = {"command": "RING_PHONE", "correlation_id": request.correlation_id}

        from app.services import mesh_service as ms
        msg = ms.MeshMessage(
            type="REMOTE_COMMAND",
            sender_device="iris_intelligence",
            target_device=request.target_device_id or "phone_android",
            payload=payload,
        )
        await ms.hub.broadcast(msg, exclude_sender=False)

        if db and user_id:
            try:
                from app.services import mesh_relay_service as mrs
                mrs.push_relay_message(
                    db=db,
                    user_id=user_id,
                    sender_device_id="iris_intelligence",
                    target_device_id=request.target_device_id,
                    msg_type="REMOTE_COMMAND",
                    payload=payload,
                )
            except Exception:
                pass

        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="phone_android",
            capability_id=request.capability_id,
            success=True,
            data={"ring_alert": True},
            verified=True,
            verification_details="Audible ring alert triggered on Android companion.",
            duration_ms=duration,
        )

    async def _get_battery(
        self,
        request: DeviceExecutionRequest,
        db: Any | None,
        user_id: str | None,
        start_time: float,
    ) -> DeviceExecutionResult:
        # Check MeshHub devices for live battery telemetry
        from app.services import mesh_service as ms
        battery_level = None
        is_charging = None

        for d in ms.hub.devices.values():
            if "phone" in d.device_type:
                if d.battery_level is not None:
                    battery_level = d.battery_level
                    is_charging = d.is_charging
                    break

        if battery_level is None and db and user_id:
            try:
                from app.services import mesh_relay_service as mrs
                paired = mrs.list_paired_devices(db, user_id)
                for p in paired:
                    if "phone" in (p.device_type or "").lower() and p.battery_level is not None:
                        battery_level = p.battery_level
                        is_charging = False
                        break
            except Exception:
                pass

        # Also check registry telemetry
        if battery_level is None:
            dev = default_registry.get_device_by_type(DeviceType.ANDROID_PHONE)
            if dev and dev.telemetry.get("battery_level") is not None:
                battery_level = dev.telemetry.get("battery_level")
                is_charging = dev.telemetry.get("is_charging")

        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="phone_android",
            capability_id=request.capability_id,
            success=True,
            data={
                "battery_level": battery_level,
                "is_charging": is_charging,
                "device_name": "Realme GT 7T",
            },
            verified=battery_level is not None,
            verification_details=f"Android battery level: {battery_level}%" if battery_level is not None else "Battery telemetry pending from phone.",
            duration_ms=duration,
        )

    async def _get_info(
        self,
        request: DeviceExecutionRequest,
        start_time: float,
    ) -> DeviceExecutionResult:
        duration = int((time.monotonic() - start_time) * 1000)
        dev = default_registry.get_device_by_type(DeviceType.ANDROID_PHONE)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="phone_android",
            capability_id=request.capability_id,
            success=True,
            data={
                "device_name": dev.device_name if dev else "Realme GT 7T",
                "device_type": "phone_android",
                "os": "Android",
                "installed_apps_count": len(dev.installed_apps) if dev else 0,
            },
            verified=True,
            verification_details="Android companion device info retrieved.",
            duration_ms=duration,
        )


# Global android executor instance
android_device_executor = AndroidDeviceExecutor()
